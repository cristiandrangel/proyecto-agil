from decimal import Decimal
from functools import lru_cache
from typing import Literal
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class BackendSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    app_env: Literal["local", "development", "test", "production"] = "local"
    public_base_url: str = "http://localhost:8080"
    public_domain: str = ""
    demo_mode: bool = True
    enable_local_message_endpoint: bool = True
    operator_username: str = "evaluador"
    operator_password: SecretStr
    session_secret: SecretStr
    central_api_url: str = "http://central:8001"
    central_operator_token: SecretStr
    central_agent_token: SecretStr
    memory_database_url_override: str | None = None
    memory_db_host: str = "memory-db"
    memory_db_port: int = 5432
    memory_db_name: str = "memory"
    memory_db_user: str = "memory"
    memory_db_password: SecretStr
    openai_api_key: SecretStr = SecretStr("")
    openai_agent_model: str = "gpt-5.6-luna"
    openai_agent_reasoning_effort: str = "high"
    openai_vision_model: str = "gpt-5.6-luna"
    openai_vision_reasoning_effort: str = "none"
    openai_transcription_model: str = "gpt-transcribe"
    openai_timeout_seconds: int = 45
    openai_max_retries: int = 0
    ai_total_budget_usd: Decimal = Decimal("5.00")
    ai_local_spend_limit_usd: Decimal = Decimal("4.50")
    ai_max_concurrent_requests: int = 2
    ai_max_calls_per_turn: int = 5
    ai_max_input_tokens: int = 12000
    ai_max_output_tokens: int = 4096
    ai_vision_max_output_tokens: int = 400
    history_visible_messages: int = 20
    chatwoot_base_url: str = ""
    chatwoot_api_token: SecretStr = SecretStr("")
    chatwoot_contacts_api_token: SecretStr = SecretStr("")
    chatwoot_contacts_base_url: str = ""
    chatwoot_account_id: int | None = None
    chatwoot_inbox_id: int | None = None
    chatwoot_webhook_secret: SecretStr = SecretStr("")
    chatwoot_auth_scheme: Literal["api_access_token", "bearer"] = "api_access_token"
    chatwoot_webhook_auth_mode: Literal["hmac", "relay"] = "hmac"
    chatwoot_relay_token: SecretStr = SecretStr("")
    chatwoot_webhook_tolerance_seconds: int = 300
    chatwoot_template_name: str = ""
    chatwoot_template_language: str = ""
    chatwoot_template_category: str = "UTILITY"
    session_ttl_seconds: int = 1800
    campaign_followup_hours: int = 24
    campaign_interval_seconds: float = 1
    worker_concurrency: int = 2
    media_allowed_hosts: str = ""
    media_max_bytes: int = 5242880
    audio_max_seconds: int = 60
    image_max_dimension: int = 2048
    langfuse_enabled: bool = True
    langfuse_base_url: str = "http://langfuse-web:3000"
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")

    @field_validator("chatwoot_account_id", "chatwoot_inbox_id", mode="before")
    @classmethod
    def empty_ids(cls, value):
        return None if value == "" else value

    @field_validator("public_base_url", "central_api_url", "chatwoot_base_url", "chatwoot_contacts_base_url")
    @classmethod
    def valid_origin(cls, value):
        if not value:
            return value
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
            raise ValueError("Se requiere un origen HTTP(S) sin credenciales, query o fragmento")
        return value.rstrip("/")

    @model_validator(mode="after")
    def enforce_limits(self):
        if not Decimal("0") < self.ai_local_spend_limit_usd <= self.ai_total_budget_usd <= Decimal("5"):
            raise ValueError("El presupuesto local debe ser positivo, <= total y <= USD 5")
        if not 1 <= self.ai_max_concurrent_requests <= 2 or not 1 <= self.ai_max_calls_per_turn <= 5:
            raise ValueError("Máximo dos inferencias simultáneas y cinco llamadas por turno")
        if self.app_env == "production":
            if not self.public_base_url.startswith("https://"):
                raise ValueError("El entorno público requiere HTTPS")
            if self.enable_local_message_endpoint:
                raise ValueError("Deshabilita la entrada de mensajes local en producción")
        for field in ("session_secret", "central_operator_token", "central_agent_token"):
            if len(getattr(self, field).get_secret_value()) < 32:
                raise ValueError(f"{field} debe tener al menos 32 caracteres")
        if self.central_operator_token == self.central_agent_token:
            raise ValueError("Operador y agente requieren credenciales distintas")
        return self

    @property
    def memory_database_url(self):
        return self.memory_database_url_override or URL.create(
            "postgresql+psycopg", username=self.memory_db_user,
            password=self.memory_db_password.get_secret_value(), host=self.memory_db_host,
            port=self.memory_db_port, database=self.memory_db_name,
        )

    @property
    def memory_conninfo(self) -> str:
        from sqlalchemy.engine import make_url
        return make_url(self.memory_database_url).set(drivername="postgresql").render_as_string(hide_password=False)


@lru_cache
def get_settings() -> BackendSettings:
    return BackendSettings()
