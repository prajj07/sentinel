from fastapi import FastAPI
from sentinel_observability import configure_observability

from app.routes import health, payments

app = FastAPI(title="Sentinel Payments", version="0.1.0")
app.include_router(health.router)
app.include_router(payments.router)
configure_observability(app, service_name="payments")
