"""Configuration helpers for the UIABot Telegram bot."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import List


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

