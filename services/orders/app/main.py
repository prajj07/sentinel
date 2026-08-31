from contextlib import asynccontextmanager

from fastapi import FastAPI
from sentinel_observability import configure_observability

from app.routes import health, orders
from app.routes.orders import _ensure_publisher


@asynccontextmanager
async def lifespan(_: FastAPI):
    await _ensure_publisher()
    yield


app = FastAPI(title="Sentinel Orders", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(orders.router)
configure_observability(app, service_name="orders")
