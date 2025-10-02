"""Example local settings for UIABot.

Rename this file to ``local_settings.py`` (keeping it inside the ``bot``
package) and adjust the values below to bake configuration directly into the
application. Any uppercase variables defined here will be exported to the
process environment at startup, allowing you to skip ``export`` commands.
"""

TELEGRAM_BOT_TOKEN = "123456:ABC-DEF"
OPENAI_API_KEY = "sk-your-key"
OPENAI_MODEL = "gpt-4o-mini"
MANAGER_CHAT_ID = 123456789
DATABASE_PATH = "data/bot.db"
ENGINEERS = [
    {"name": "Инженер А", "chat_id": 111111111},
    {"name": "Инженер Б", "chat_id": 222222222},
]
