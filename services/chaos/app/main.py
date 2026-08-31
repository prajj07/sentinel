from fastapi import FastAPI
from sentinel_observability import configure_observability

from app.routes import chaos, health

app = FastAPI(title="Sentinel Chaos Engine", version="0.1.0")
app.include_router(health.router)
app.include_router(chaos.router)
configure_observability(app, service_name="chaos")
