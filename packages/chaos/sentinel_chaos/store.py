from __future__ import annotations

import threading
from datetime import datetime, timezone

from sentinel_chaos.models import ActiveRule


class ActiveRuleStore:
    """Process-local active fault. One rule at a time."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._rule: ActiveRule | None = None

    def activate(self, rule: ActiveRule) -> None:
        with self._lock:
            self._rule = rule

    def deactivate(self, experiment_id: str | None = None) -> ActiveRule | None:
        with self._lock:
            current = self._rule
            if current is None:
                return None
            if experiment_id is not None and current.experiment_id != experiment_id:
                return None
            self._rule = None
            return current

    def deactivate_any(self) -> ActiveRule | None:
        with self._lock:
            current = self._rule
            self._rule = None
            return current

    def get_active(self) -> ActiveRule | None:
        with self._lock:
            rule = self._rule
            if rule is None:
                return None
            if datetime.now(timezone.utc) >= rule.expires_at:
                self._rule = None
                return None
            return rule


store = ActiveRuleStore()
