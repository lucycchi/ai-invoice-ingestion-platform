"""Settings, read from the environment and the project's .env file."""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingSetting(Exception):
    """A required setting is missing; the app must not start."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-opus-5-5"
    reference_api_url: str = "http://api:8000"
    data_dir: Path = Path("/data")
    # Only these host names are served, which blocks DNS-rebinding attacks from other websites.
    allowed_hosts: list[str] = ["localhost", "127.0.0.1"]
    # The address the server listens on: this machine only, unless the container sets 0.0.0.0.
    host: str = "127.0.0.1"


def get_settings(env_file: str | None = ".env") -> Settings:
    """Load the settings, refusing to go on without an Anthropic API key."""
    settings = Settings(_env_file=env_file)
    if not settings.anthropic_api_key.get_secret_value().strip():
        raise MissingSetting(
            "ANTHROPIC_API_KEY is missing. Set it in the .env file in the project root "
            "(copy .env.example to .env and paste your key)."
        )
    return settings
