"""Entrypoint for running the UIABot Telegram bot."""

from __future__ import annotations

import logging
from pathlib import Path

from .ai import AIAssistant
from .config import load_config, load_env_file
from .database import Database
from .handlers import build_application


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    # Load optional .env configuration before reading environment variables.
    project_root = Path(__file__).resolve().parent.parent
    load_env_file(str(project_root / ".env"))
    if Path.cwd().resolve() != project_root:
        load_env_file(".env")

    config = load_config()
    database = Database(config.database_path)
    assistant = AIAssistant(config.openai_api_key, model=config.openai_model)
    application = build_application(config, database, assistant)
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()

