from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "chaos"
    gateway_url: str = "http://gateway:8000"
    orders_url: str = "http://orders:8001"
    inventory_url: str = "http://inventory:8002"
    payments_url: str = "http://payments:8003"


@lru_cache
def get_settings() -> Settings:
    return Settings()
