from pathlib import Path

import pytest

from app.config import Settings

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings(tmp_path):
    """Settings for one test: a fake key and a throwaway data folder."""
    return Settings(anthropic_api_key="sk-test-SECRET123", data_dir=tmp_path / "data")
