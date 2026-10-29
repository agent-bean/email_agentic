from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[5]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore", hide_input_in_errors=True)
    environment: str = Field("production", alias="APP_ENV")
    owner_email: str = Field("", alias="GOOGLE_TEST_ACCOUNT_EMAIL")
    app_origin: str = "http://127.0.0.1:8000"
    cf_team_domain: str = ""
    cf_audience: str = ""
    database_url: SecretStr = SecretStr("")
    postgres_password: SecretStr = SecretStr("")
    postgres_host: str = "127.0.0.1"
    data_dir: Path = ROOT / ".runtime/app"
    llm_base_url: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = ""
    tavily_api_key: SecretStr = SecretStr("")
    firecrawl_api_key: SecretStr = SecretStr("")
    firecrawl_max_pages: int = Field(12, ge=0, le=30)
    google_oauth_token_file: Path = Path(".secrets/google/token.json")
    google_calendar_id: str = "primary"
    report_target_seconds: float = Field(42, gt=0)
    research_timeout_seconds: float = Field(180, gt=0)
    tool_limit_per_minute: int = Field(60, gt=0)
    app_timezone: str = "Asia/Bangkok"
    telemetry_endpoint: str = ""
    local_client_hosts: str = "127.0.0.1,::1,testclient"
    scheduler_enabled: bool = False

    @field_validator("research_timeout_seconds", mode="before")
    @classmethod
    def empty_timeout(cls, value):
        return 180 if value == "" else value

    @model_validator(mode="after")
    def validate_security(self):
        if self.environment not in {"local", "production", "test"}:
            raise ValueError("APP_ENV must be local, production or test")
        if self.environment == "production" and not (self.cf_team_domain and self.cf_audience):
            raise ValueError("Production requires CF_TEAM_DOMAIN and CF_AUDIENCE")
        return self

    @property
    def dsn(self):
        if self.database_url.get_secret_value():
            return self.database_url.get_secret_value()
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return f"postgresql://email_agentic:{password}@{self.postgres_host}:5432/email_agentic"

    @property
    def google_token_path(self):
        path = self.google_oauth_token_file
        return path if path.is_absolute() else ROOT / path


@lru_cache
def get_settings():
    return Settings()
