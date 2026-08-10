from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.consumer import start_consumer, stop_consumer
from app.routes import health, notifications


@asynccontextmanager
async def lifespan(_: FastAPI):
    await start_consumer()
    yield
    await stop_consumer()


app = FastAPI(title="Sentinel Notifications", version="0.1.0", lifespan=lifespan)
app.include_router(health.router)
app.include_router(notifications.router)
