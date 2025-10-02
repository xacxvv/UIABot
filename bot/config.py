"""Configuration helpers for the UIABot Telegram bot."""

from __future__ import annotations

import importlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Engineer:
    """Represents an engineer who can receive escalated tickets."""

    name: str
    chat_id: int


@dataclass(frozen=True)
class BotConfig:
    """Holds configuration for the Telegram bot."""

    telegram_token: str
    openai_api_key: str
    manager_chat_id: int
    engineers: List[Engineer]
    openai_model: str = "gpt-4o-mini"
    database_path: str = "data/bot.db"


def _load_engineers(raw: str | None) -> List[Engineer]:
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(
            "ENGINEERS environment variable must contain valid JSON"
        ) from exc

    engineers: List[Engineer] = []
    for item in payload:
        if "name" not in item or "chat_id" not in item:
            raise ValueError(
                "Each engineer definition must contain 'name' and 'chat_id' keys"
            )
        engineers.append(Engineer(name=str(item["name"]), chat_id=int(item["chat_id"])))
    return engineers


def apply_local_settings(module_name: str = "bot.local_settings") -> None:
    """Populate environment variables from a Python settings module.

    Operators who prefer to store configuration directly in code can create a
    ``bot/local_settings.py`` file containing uppercase variables (for example
    ``TELEGRAM_BOT_TOKEN = "123"``). When present the values are copied into the
    environment unless they are already defined, preserving ad-hoc overrides.
    Complex structures such as ``ENGINEERS`` can be expressed with native Python
    literals and are serialized to JSON before being exported.
    """

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError:
        return
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to import %s: %s", module_name, exc)
        return

    for key in dir(module):
        if not key.isupper():
            continue
        value = getattr(module, key)
        if value is None:
            continue
        if isinstance(value, (dict, list)):
            serialized = json.dumps(value, ensure_ascii=False)
        else:
            serialized = str(value)
        os.environ.setdefault(key, serialized)


def load_env_file(path: str | None = None) -> None:
    """Load environment variables from a dotenv-style file.

    Parameters
    ----------
    path:
        Optional override pointing to a file containing KEY=VALUE pairs. When
        omitted the function looks for ``UIABOT_ENV_FILE`` in the environment
        and falls back to ``.env`` located in the repository root.
    """

    candidate = path or os.environ.get("UIABOT_ENV_FILE", ".env")
    candidate_path = Path(candidate)
    if not candidate_path.is_absolute():
        project_root = Path(__file__).resolve().parents[1]
        candidate_path = project_root / candidate_path

    if not candidate_path.exists():
        return

    try:
        with candidate_path.open(encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    logger.warning("Ignoring malformed line in %s: %s", candidate_path, raw_line.rstrip())
                    continue

                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
                    value = value[1:-1]

                if key and key not in os.environ:
                    os.environ[key] = value
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Failed to load environment file %s: %s", candidate_path, exc)


def load_config() -> BotConfig:
    """Load configuration from environment variables."""

    telegram_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not telegram_token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is required")

    openai_api_key = os.environ.get("OPENAI_API_KEY")
    if not openai_api_key:
        raise ValueError("OPENAI_API_KEY environment variable is required")

    manager_raw = os.environ.get("MANAGER_CHAT_ID")
    if not manager_raw:
        raise ValueError("MANAGER_CHAT_ID environment variable is required")
    manager_chat_id = int(manager_raw)

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    engineers = _load_engineers(os.environ.get("ENGINEERS"))

    db_path = os.environ.get("DATABASE_PATH", "data/bot.db")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    return BotConfig(
        telegram_token=telegram_token,
        openai_api_key=openai_api_key,
        openai_model=model,
        manager_chat_id=manager_chat_id,
        engineers=engineers,
        database_path=db_path,
    )

