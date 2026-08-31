from __future__ import annotations

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import get_settings
from app.telemetry import percentile, snapshot_order_payment_metrics

ORDER_BODY = {
    "customer_id": "chaos_scenario",
    "items": [{"product_id": "prod_001", "quantity": 1}],
    "amount": 100,
}


def _place_order(gateway_url: str, timeout: float) -> tuple[int, float]:
    started = time.perf_counter()
    with httpx.Client(timeout=timeout) as client:
        try:
            response = client.post(f"{gateway_url.rstrip('/')}/orders", json=ORDER_BODY)
            status = response.status_code
        except httpx.HTTPError:
            status = 0
    return status, time.perf_counter() - started


def _run_traffic(gateway_url: str, count: int, timeout: float, workers: int) -> list[tuple[int, float]]:
    results: list[tuple[int, float]] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_place_order, gateway_url, timeout) for _ in range(count)]
        for future in as_completed(futures):
            results.append(future.result())
    return results


def _summarize(results: list[tuple[int, float]]) -> dict[str, Any]:
    durations = [duration for _, duration in results]
    failures = sum(1 for status, _ in results if status != 200)
    return {
        "count": len(results),
        "failures": failures,
        "error_rate": (failures / len(results)) if results else 0.0,
        "p95_s": percentile(durations, 0.95),
        "mean_s": (sum(durations) / len(durations)) if durations else 0.0,
    }


def _format_report(
    experiment_id: str,
    delay_ms: int,
    duration_seconds: int,
    baseline: dict[str, Any],
    impact: dict[str, Any],
    recovery: dict[str, Any],
    recovery_seconds: float,
    passed: bool,
) -> str:
    result = "PASSED" if passed else "FAILED"
    closing = (
        "System degraded as expected and recovered\nafter the failure was removed."
        if passed
        else "Impact or recovery did not meet expected thresholds."
    )
    return (
        f"CHAOS EXPERIMENT #{experiment_id.upper()}\n"
        f"\n"
        f"Target:\n"
        f"Payments\n"
        f"\n"
        f"Failure:\n"
        f"{delay_ms / 1000:.0f}s latency\n"
        f"\n"
        f"Duration:\n"
        f"{duration_seconds}s\n"
        f"\n"
        f"Impact:\n"
        f"Order P95     {baseline['p95_s'] * 1000:.0f}ms → {impact['p95_s']:.1f}s\n"
        f"Error rate      {baseline['error_rate'] * 100:.1f}% → {impact['error_rate'] * 100:.1f}%\n"
        f"\n"
        f"Recovery:\n"
        f"{recovery_seconds:.0f} seconds (post-stop P95 {recovery['p95_s'] * 1000:.0f}ms)\n"
        f"\n"
        f"Result:\n"
        f"{result}\n"
        f"\n"
        f"{closing}\n"
    )


async def run_payment_degradation(
    *,
    inject,
    stop,
    delay_ms: int = 3000,
    duration_seconds: int = 30,
    baseline_orders: int = 6,
    traffic_orders: int = 8,
    recovery_orders: int = 4,
) -> dict[str, Any]:
    """Run the payment-degradation scenario against the live stack."""
    settings = get_settings()
    gateway = settings.gateway_url
    timeout = 15.0

    loop = asyncio.get_running_loop()

    def baseline_and_impact() -> tuple[list[tuple[int, float]], dict[str, Any]]:
        with httpx.Client(timeout=timeout) as http:
            before_metrics = snapshot_order_payment_metrics(
                http, settings.orders_url, settings.payments_url
            )
        baseline_results = _run_traffic(gateway, baseline_orders, timeout, workers=2)
        return baseline_results, before_metrics

    baseline_results, before_metrics = await loop.run_in_executor(None, baseline_and_impact)
    baseline = _summarize(baseline_results)

    experiment = await inject(
        {
            "service": "payments",
            "type": "latency",
            "duration_seconds": duration_seconds,
            "delay_ms": delay_ms,
        }
    )
    experiment_id = experiment["experiment_id"]

    during_metrics: dict[str, Any] = {}
    try:
        impact_results = await loop.run_in_executor(
            None,
            lambda: _run_traffic(gateway, traffic_orders, timeout, workers=8),
        )
        impact = _summarize(impact_results)

        with httpx.Client(timeout=timeout) as http:
            during_metrics = snapshot_order_payment_metrics(
                http, settings.orders_url, settings.payments_url
            )
    finally:
        stop_started = time.perf_counter()
        await stop(experiment_id)

    recovery_results = await loop.run_in_executor(
        None,
        lambda: _run_traffic(gateway, recovery_orders, timeout, workers=2),
    )
    recovery = _summarize(recovery_results)
    recovery_seconds = time.perf_counter() - stop_started

    degraded = impact["p95_s"] >= max(baseline["p95_s"] * 3, (delay_ms / 1000.0) * 0.6)
    recovered = recovery["p95_s"] < impact["p95_s"] * 0.5
    passed = degraded and recovered

    impact_summary = {
        "order_p95_ms": {
            "before": round(baseline["p95_s"] * 1000, 1),
            "after": round(impact["p95_s"] * 1000, 1),
            "recovery": round(recovery["p95_s"] * 1000, 1),
        },
        "orders_failed_rate": {
            "before": round(baseline["error_rate"], 4),
            "after": round(impact["error_rate"], 4),
        },
        "metrics_before": before_metrics,
        "metrics_during": during_metrics,
        "recovery_seconds": round(recovery_seconds, 2),
        "result": "PASSED" if passed else "FAILED",
    }

    report_text = _format_report(
        experiment_id,
        delay_ms,
        duration_seconds,
        baseline,
        impact,
        recovery,
        recovery_seconds,
        passed,
    )

    return {
        "experiment_id": experiment_id,
        "service": "payments",
        "type": "latency",
        "duration_seconds": duration_seconds,
        "delay_ms": delay_ms,
        "status": "completed",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "impact_summary": impact_summary,
        "baseline": baseline,
        "impact": impact,
        "recovery": recovery,
        "result": "PASSED" if passed else "FAILED",
        "report": report_text,
    }
