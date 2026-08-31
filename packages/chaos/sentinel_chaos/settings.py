from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChaosSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    chaos_enabled: bool = False


@lru_cache
def get_chaos_settings() -> ChaosSettings:
    return ChaosSettings()
