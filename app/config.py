from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FTMS_",
        extra="ignore",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ftms"
    controller_base_url: str = "http://localhost:8001"
    controller_mode: str = "simulator"  # "simulator" | "rest"
    log_level: str = "INFO"

    green_seconds: int = 30
    yellow_seconds: int = 5
    all_red_seconds: int = 3

    manual_override_seconds: int = 60
    emergency_max_seconds: int = 120

    command_timeout_seconds: int = 5
    command_max_retries: int = 3

    scheduler_tick_seconds: float = 0.5

    starvation_seconds: int = 90
    wait_time_boost: float = 0.5


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()