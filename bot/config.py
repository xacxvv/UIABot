"""Configuration helpers for the UIABot Telegram bot."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List, Set


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
    openai_model: str
    manager_chat_id: int
    engineers: List[Engineer]
    employee_codes: Set[str]
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


def _load_employee_codes(raw: str | None) -> Set[str]:
    if not raw:
        return set()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(
            "EMPLOYEE_CODES environment variable must contain valid JSON"
        ) from exc

    if isinstance(payload, list):
        codes = {str(item).strip() for item in payload if str(item).strip()}
        return codes

    if isinstance(payload, dict):
        codes = {str(key).strip() for key, value in payload.items() if str(key).strip()}
        return codes

    raise ValueError(
        "EMPLOYEE_CODES environment variable must be a JSON array or object"
    )


def load_env_file(path: str) -> None:
    """Load environment variables from a ``.env`` style file.

    The parser is intentionally minimal: blank lines and comments are ignored,
    keys and values are stripped from surrounding whitespace, quoted values are
    unwrapped, and values for keys that already exist in ``os.environ`` are not
    overwritten ("first wins").

    In addition to the classic ``KEY=VALUE`` form, lines starting with
    ``export`` are also accepted which allows compatibility with shells where
    environment files use ``export KEY=VALUE`` assignments.
    """

    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue

            if line.startswith("export"):
                remainder = line[6:]
                if remainder and remainder[0].isspace():
                    line = remainder.lstrip()

            if "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()

            if not key or key in os.environ:
                continue

            if value and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]

            os.environ[key] = value


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

    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    engineers = _load_engineers(os.environ.get("ENGINEERS"))
    employee_codes = _load_employee_codes(os.environ.get("EMPLOYEE_CODES"))

    db_path = os.environ.get("DATABASE_PATH", "data/bot.db")
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    return BotConfig(
        telegram_token=telegram_token,
        openai_api_key=openai_api_key,
        openai_model=openai_model,
        manager_chat_id=manager_chat_id,
        engineers=engineers,
        employee_codes=employee_codes,
        database_path=db_path,
    )

