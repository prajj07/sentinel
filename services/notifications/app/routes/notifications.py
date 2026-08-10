from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory receipts for Sprint 1 testing (no DB)
_received_events: list[dict[str, Any]] = []


def get_received_events() -> list[dict[str, Any]]:
    return list(_received_events)


def clear_received_events() -> None:
    _received_events.clear()


def record_event(payload: dict[str, Any]) -> None:
    _received_events.append(payload)
    logger.info("notification received: %s", json.dumps(payload, default=str))


@router.get("/notifications/received")
def list_received() -> dict[str, Any]:
    return {"count": len(_received_events), "events": _received_events}


@router.delete("/notifications/received")
def reset_received() -> dict[str, str]:
    clear_received_events()
    return {"status": "cleared"}
