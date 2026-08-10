from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "gateway"
    orders_url: str = "http://orders:8001"
    gateway_http_timeout_seconds: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
