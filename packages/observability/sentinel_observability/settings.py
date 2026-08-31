from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ObservabilitySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    otel_exporter_otlp_endpoint: str = "http://tempo:4317"
    otel_traces_exporter: str = "otlp"
    otel_metrics_exporter: str = "none"
    otel_logs_exporter: str = "none"
    otel_service_name: str = "sentinel"
    otel_enabled: bool = True


@lru_cache
def get_observability_settings() -> ObservabilitySettings:
    return ObservabilitySettings()
