from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://sentinel:sentinel@postgres:5432/sentinel"


class RedisSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    redis_url: str = "redis://redis:6379/0"
    inventory_cache_ttl_seconds: int = 60


class RabbitMQSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    rabbitmq_url: str = "amqp://sentinel:sentinel@rabbitmq:5672/"
    rabbitmq_exchange: str = "sentinel.events"


class HttpSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    http_timeout_seconds: float = 5.0
    gateway_http_timeout_seconds: float = 10.0


@lru_cache
def get_database_settings() -> DatabaseSettings:
    return DatabaseSettings()


@lru_cache
def get_redis_settings() -> RedisSettings:
    return RedisSettings()


@lru_cache
def get_rabbitmq_settings() -> RabbitMQSettings:
    return RabbitMQSettings()


@lru_cache
def get_http_settings() -> HttpSettings:
    return HttpSettings()
