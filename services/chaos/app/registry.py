from __future__ import annotations

import threading
from datetime import datetime, timezone

from sentinel_chaos.models import ExperimentRecord, ExperimentStatus


class ExperimentRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._experiments: dict[str, ExperimentRecord] = {}

    def add(self, record: ExperimentRecord) -> ExperimentRecord:
        with self._lock:
            self._experiments[record.id] = record
            return record

    def get(self, experiment_id: str) -> ExperimentRecord | None:
        with self._lock:
            return self._experiments.get(experiment_id)

    def list(self) -> list[ExperimentRecord]:
        with self._lock:
            records = list(self._experiments.values())
        return sorted(records, key=lambda r: r.started_at, reverse=True)

    def update_status(
        self,
        experiment_id: str,
        status: ExperimentStatus,
        *,
        error: str | None = None,
        impact_summary: dict | None = None,
    ) -> ExperimentRecord | None:
        with self._lock:
            record = self._experiments.get(experiment_id)
            if record is None:
                return None
            record.status = status
            record.ended_at = datetime.now(timezone.utc)
            if error is not None:
                record.error = error
            if impact_summary is not None:
                record.impact_summary = impact_summary
            return record


registry = ExperimentRegistry()
