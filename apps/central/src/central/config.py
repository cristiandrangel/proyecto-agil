from functools import lru_cache
from urllib.parse import quote_plus

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", case_sensitive=False, hide_input_in_errors=True
    )
    central_database_url: str | None = None
    central_db_host: str = "localhost"
    central_db_port: int = 5432
    central_db_name: str = "central"
    central_db_user: str = "central"
    central_db_password: SecretStr = SecretStr("")
    central_operator_token: SecretStr = SecretStr("")
    central_agent_token: SecretStr = SecretStr("")
    payment_signing_key: SecretStr = SecretStr("")
    demo_mode: bool = True
    demo_pin: SecretStr = SecretStr("2468")
    session_ttl_seconds: int = 1800
    order_ttl_seconds: int = 1800
    receipt_ttl_seconds: int = 86400
    pin_max_attempts: int = 3
    pin_lock_seconds: int = 900

    @model_validator(mode="after")
    def validate_security(self):
        operator = self.central_operator_token.get_secret_value()
        agent = self.central_agent_token.get_secret_value()
        if operator and operator == agent:
            raise ValueError("Central operator and agent credentials must differ")
        if (
            min(
                self.session_ttl_seconds,
                self.order_ttl_seconds,
                self.receipt_ttl_seconds,
                self.pin_max_attempts,
                self.pin_lock_seconds,
            )
            <= 0
        ):
            raise ValueError("Expiry and attempt limits must be positive")
        return self

    @property
    def database_url(self):
        if self.central_database_url:
            return self.central_database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        password = quote_plus(self.central_db_password.get_secret_value())
        return f"postgresql+psycopg://{self.central_db_user}:{password}@{self.central_db_host}:{self.central_db_port}/{self.central_db_name}"


@lru_cache
def get_settings():
    return Settings()
