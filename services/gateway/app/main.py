from fastapi import FastAPI

from app.routes import health, orders

app = FastAPI(title="Sentinel Gateway", version="0.1.0")
app.include_router(health.router)
app.include_router(orders.router)
