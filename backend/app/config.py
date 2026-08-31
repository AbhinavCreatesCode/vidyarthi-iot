"""
Centralised settings, loaded from environment variables / a .env file.
Nothing else in the app should call os.environ directly -- import `settings`.
"""

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # PostgreSQL / Supabase
    database_url: str = ""
    db_pool_min_size: int = 1
    db_pool_max_size: int = 8

    # Telegram
    telegram_bot_token: str = ""
    telegram_dry_run: bool = True
    telegram_webhook_secret: str = ""

    data_dir: str = "./data"

    # Attendance
    am_pm_cutoff_hour: int = 12

    # PM-POSHAN
    grain_g_per_child: int = 100
    pulses_g_per_child: int = 20
    # Default stock for a new school day. Dashboard can overwrite these values.
    ration_initial_grain_kg: float = 0.0
    ration_initial_pulses_kg: float = 0.0

    # Dropout / equity
    dropout_missed_threshold: int = 5
    rabi_months: str = "11,12,1"
    kharif_months: str = "6,7,8,9"

    # SMS gateway
    sms_gateway_url: str = ""
    sms_gateway_api_key: str = ""
    sms_sender_id: str = "SCHOOL"
    sms_dry_run: bool = True
    sms_batch_hour: int = 19
    sms_batch_minute: int = 30

    # Security
    admin_api_key: str = ""
    terminal_api_key: str = ""
    # CORS
    cors_origins: str = "*"

    @property
    def rabi_months_list(self) -> List[int]:
        return [int(m) for m in self.rabi_months.split(",") if m.strip()]

    @property
    def kharif_months_list(self) -> List[int]:
        return [int(m) for m in self.kharif_months.split(",") if m.strip()]

    @property
    def cors_origins_list(self) -> List[str]:
        raw = self.cors_origins.strip()
        if raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
