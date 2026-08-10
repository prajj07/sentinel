from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "notifications"
    rabbitmq_url: str = "amqp://sentinel:sentinel@rabbitmq:5672/"
    rabbitmq_exchange: str = "sentinel.events"


@lru_cache
def get_settings() -> Settings:
    return Settings()
