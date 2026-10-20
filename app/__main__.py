"""Starts the app server: `python -m app`."""

import sys

import uvicorn

from app.config import MissingSetting, get_settings
from app.main import create_app


def main() -> None:
    try:
        settings = get_settings()
    except MissingSetting as err:
        print(err, file=sys.stderr)
        sys.exit(1)
    uvicorn.run(create_app(settings), host="0.0.0.0", port=8080)


if __name__ == "__main__":
    main()
