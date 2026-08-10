from fastapi import APIRouter, HTTPException

from app.config import get_settings
from sentinel_common.http_client import DownstreamError, DownstreamTimeoutError, request_json
from sentinel_contracts.orders import CreateOrderRequest, CreateOrderResponse

router = APIRouter()


@router.post("/orders", response_model=CreateOrderResponse)
async def create_order(payload: CreateOrderRequest) -> CreateOrderResponse:
    settings = get_settings()
    url = f"{settings.orders_url.rstrip('/')}/orders"

    try:
        status_code, body = await request_json(
            "POST",
            url,
            json_body=payload.model_dump(mode="json"),
            timeout_seconds=settings.gateway_http_timeout_seconds,
        )
    except DownstreamTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except DownstreamError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    if status_code >= 400:
        detail = body if isinstance(body, (dict, list, str)) else "Orders service error"
        raise HTTPException(status_code=status_code, detail=detail)

    return CreateOrderResponse.model_validate(body)
