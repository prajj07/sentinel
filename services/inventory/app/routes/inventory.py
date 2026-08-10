from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from sentinel_common.db import get_session
from sentinel_common.models import InventoryItem
from sentinel_common.redis_cache import (
    get_cached_inventory,
    invalidate_cached_inventory,
    set_cached_inventory,
)
from sentinel_contracts.orders import (
    InventoryResponse,
    ReserveInventoryRequest,
    ReserveInventoryResponse,
)

router = APIRouter()


@router.get("/inventory/{product_id}", response_model=InventoryResponse)
def get_inventory(
    product_id: str,
    session: Session = Depends(get_session),
) -> InventoryResponse:
    cached = get_cached_inventory(product_id)
    if cached is not None:
        return InventoryResponse(
            product_id=cached["product_id"],
            available_quantity=cached["available_quantity"],
            cache_hit=True,
        )

    item = session.scalar(select(InventoryItem).where(InventoryItem.product_id == product_id))
    if item is None:
        raise HTTPException(status_code=404, detail=f"Product '{product_id}' not found")

    payload = {
        "product_id": item.product_id,
        "available_quantity": item.available_quantity,
    }
    set_cached_inventory(product_id, payload)
    return InventoryResponse(
        product_id=item.product_id,
        available_quantity=item.available_quantity,
        cache_hit=False,
    )


@router.post("/inventory/reserve", response_model=ReserveInventoryResponse)
def reserve_inventory(
    payload: ReserveInventoryRequest,
    session: Session = Depends(get_session),
) -> ReserveInventoryResponse:
    item = session.scalar(
        select(InventoryItem)
        .where(InventoryItem.product_id == payload.product_id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(status_code=404, detail=f"Product '{payload.product_id}' not found")

    if item.available_quantity < payload.quantity:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Insufficient inventory",
                "product_id": payload.product_id,
                "requested": payload.quantity,
                "available": item.available_quantity,
            },
        )

    item.available_quantity -= payload.quantity
    item.updated_at = datetime.now(timezone.utc)
    session.commit()
    session.refresh(item)

    invalidate_cached_inventory(payload.product_id)
    set_cached_inventory(
        payload.product_id,
        {
            "product_id": item.product_id,
            "available_quantity": item.available_quantity,
        },
    )

    return ReserveInventoryResponse(
        product_id=item.product_id,
        reserved_quantity=payload.quantity,
        available_quantity=item.available_quantity,
    )
