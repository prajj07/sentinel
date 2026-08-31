from fastapi import FastAPI
from sentinel_observability import configure_observability

from app.routes import health, inventory

app = FastAPI(title="Sentinel Inventory", version="0.1.0")
app.include_router(health.router)
app.include_router(inventory.router)
configure_observability(app, service_name="inventory")
