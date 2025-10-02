"""Entrypoint for running the UIABot Telegram bot."""

from __future__ import annotations

import logging

from .ai import AIAssistant
from .config import load_config, load_env_file
from .database import Database
from .handlers import build_application


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main() -> None:
    load_env_file()
    config = load_config()
    database = Database(config.database_path)
    assistant = AIAssistant(config.openai_api_key, model=config.openai_model)
    if not assistant.verify_model():
        logging.error(
            "Configured OpenAI model '%s' is not accessible. Update OPENAI_MODEL or the API key.",
            config.openai_model,
        )
        raise SystemExit(1)
    application = build_application(config, database, assistant)
    application.run_polling()


if __name__ == "__main__":  # pragma: no cover - script entry point
    main()

