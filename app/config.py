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


def get_settings(env_file: str | None = ".env") -> Settings:
    """Load the settings, refusing to go on without an Anthropic API key."""
    settings = Settings(_env_file=env_file)
    if not settings.anthropic_api_key.get_secret_value().strip():
        raise MissingSetting(
            "ANTHROPIC_API_KEY is missing. Set it in the .env file in the project root "
            "(copy .env.example to .env and paste your key)."
        )
    return settings
