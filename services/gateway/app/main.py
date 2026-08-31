from fastapi import FastAPI
from sentinel_observability import configure_observability

from app.routes import health, orders

app = FastAPI(title="Sentinel Gateway", version="0.1.0")
app.include_router(health.router)
app.include_router(orders.router)
configure_observability(app, service_name="gateway")
