from fastapi import FastAPI

from app.routes import health, payments

app = FastAPI(title="Sentinel Payments", version="0.1.0")
app.include_router(health.router)
app.include_router(payments.router)
