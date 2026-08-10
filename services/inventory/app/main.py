from fastapi import FastAPI

from app.routes import health, inventory

app = FastAPI(title="Sentinel Inventory", version="0.1.0")
app.include_router(health.router)
app.include_router(inventory.router)
