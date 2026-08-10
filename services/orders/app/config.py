from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "orders"
    inventory_url: str = "http://inventory:8002"
    payments_url: str = "http://payments:8003"
    http_timeout_seconds: float = 5.0
    rabbitmq_url: str = "amqp://sentinel:sentinel@rabbitmq:5672/"
    rabbitmq_exchange: str = "sentinel.events"


@lru_cache
def get_settings() -> Settings:
    return Settings()
