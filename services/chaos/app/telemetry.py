from __future__ import annotations

import math
import re
from typing import Any

import httpx


def parse_counter(metrics: str, name: str) -> float:
    prefix = f"{name} "
    labeled = f"{name}{{"
    for line in metrics.splitlines():
        if line.startswith("#"):
            continue
        if line.startswith(prefix) or line.startswith(labeled):
            parts = line.split()
            if len(parts) >= 2:
                return float(parts[-1])
    return 0.0


def parse_histogram_quantile(metrics: str, name: str, quantile: float = 0.95) -> float | None:
    """Approximate a histogram quantile from Prometheus exposition format."""
    buckets: list[tuple[float, float]] = []
    count = 0.0
    bucket_re = re.compile(rf'^{re.escape(name)}_bucket\{{[^}}]*le="([^"]+)"[^}}]*\}}\s+([0-9.eE+-]+)')
    count_re = re.compile(rf"^{re.escape(name)}_count(?:\{{[^}}]*\}})?\s+([0-9.eE+-]+)")
    for line in metrics.splitlines():
        match = bucket_re.match(line)
        if match:
            le = match.group(1)
            value = float(match.group(2))
            bound = float("inf") if le == "+Inf" else float(le)
            buckets.append((bound, value))
            continue
        match = count_re.match(line)
        if match:
            count = float(match.group(1))
    if not buckets or count <= 0:
        return None
    buckets.sort(key=lambda item: item[0])
    target = quantile * count
    for bound, cumulative in buckets:
        if cumulative >= target:
            return bound if math.isfinite(bound) else buckets[-2][0] if len(buckets) > 1 else bound
    return buckets[-1][0]


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return ordered[index]


def scrape_metrics(http: httpx.Client, base_url: str) -> str:
    response = http.get(f"{base_url.rstrip('/')}/metrics")
    response.raise_for_status()
    return response.text


def snapshot_order_payment_metrics(http: httpx.Client, orders_url: str, payments_url: str) -> dict[str, Any]:
    orders = scrape_metrics(http, orders_url)
    payments = scrape_metrics(http, payments_url)
    return {
        "orders_created_total": parse_counter(orders, "orders_created_total"),
        "orders_failed_total": parse_counter(orders, "orders_failed_total"),
        "order_p95_s": parse_histogram_quantile(orders, "order_duration_seconds"),
        "payments_failed_total": parse_counter(payments, "payments_failed_total"),
        "payment_p95_s": parse_histogram_quantile(payments, "http_request_duration_seconds"),
    }
