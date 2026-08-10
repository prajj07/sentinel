from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "inventory"
    database_url: str = "postgresql+psycopg://sentinel:sentinel@postgres:5432/sentinel"
    redis_url: str = "redis://redis:6379/0"
    inventory_cache_ttl_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()
