from fastapi import APIRouter

from app.config import get_settings
from sentinel_contracts.orders import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(service=settings.service_name, status="healthy")
