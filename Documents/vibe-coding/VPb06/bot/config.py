from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

# Загружаем переменные из существующего файла `.env`.
# Файл `.env` уже предполагается существующим (см. .cursorignore).
load_dotenv()


# Токен Telegram-бота (обязательно должен быть в `.env`).
BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден. Заполните переменную BOT_TOKEN в файле .env")


def _default_database_path() -> Path:
    """
    Возвращает путь к SQLite базе.

    Если `DATABASE_PATH` указано относительным путём, считаем что база лежит в корне проекта.
    """

    root_dir = Path(__file__).resolve().parent.parent
    value = os.getenv("DATABASE_PATH", "tasks.db").strip()
    p = Path(value)
    return p if p.is_absolute() else (root_dir / p)


DATABASE_PATH: Path = _default_database_path()

