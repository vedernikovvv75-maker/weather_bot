from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from bot.config import DATABASE_PATH


def init_db(db_path: Path = DATABASE_PATH) -> None:
    """
    Создаёт таблицу `tasks`, если её ещё нет.

    Таблица:
      - id (INTEGER, primary key)
      - text (TEXT): текст задачи
      - user (TEXT): Telegram user id (строкой)
      - created_at (TEXT): время добавления (по умолчанию datetime('now'))
    """

    # check_same_thread=False не нужен, т.к. доступ к БД происходит синхронно
    # внутри `asyncio.to_thread(...)`.
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              text TEXT NOT NULL,
              user TEXT NOT NULL,
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_tasks_created_at ON tasks(created_at, id);")


def add_task(text: str, user: str, db_path: Path = DATABASE_PATH) -> int:
    """
    Добавляет новую задачу в таблицу и возвращает её `id`.

    Аргументы:
      - text: текст задачи
      - user: Telegram user id (строкой)
    """

    text = text.strip()
    if not text:
        raise ValueError("text не должен быть пустым")

    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "INSERT INTO tasks(text, user) VALUES(?, ?);",
            (text, user),
        )
        # SQLite запоминает lastrowid у курсора после INSERT.
        return int(cur.lastrowid)


def get_tasks(db_path: Path = DATABASE_PATH) -> list[dict[str, Any]]:
    """
    Возвращает список всех задач.

    Требование:
      - порядок добавления (сортировка по created_at, затем id)
    """

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, text, user, created_at FROM tasks ORDER BY created_at ASC, id ASC;"
        ).fetchall()

    return [dict(row) for row in rows]

