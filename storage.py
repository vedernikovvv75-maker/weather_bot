from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import Any


class StorageError(RuntimeError):
    """Raised when cache file cannot be read or written."""


def save_to_file(data: dict[str, Any], path: str = "currency_rate.json") -> None:
    try:
        with open(path, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
    except OSError as error:
        raise StorageError(f"Не удалось сохранить кэш в {path}.") from error


def read_from_file(path: str = "currency_rate.json") -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except FileNotFoundError as error:
        raise StorageError(f"Файл кэша {path} не найден.") from error
    except json.JSONDecodeError as error:
        raise StorageError(f"Файл кэша {path} поврежден (невалидный JSON).") from error
    except OSError as error:
        raise StorageError(f"Не удалось прочитать файл кэша {path}.") from error

    if not isinstance(data, dict):
        raise StorageError(f"Файл кэша {path} имеет неверный формат.")
    return data


def is_cache_fresh(path: str = "currency_rate.json", max_age_hours: int = 24) -> bool:
    file_path = Path(path)
    if not file_path.exists():
        return False
    age_seconds = time() - file_path.stat().st_mtime
    return age_seconds < max_age_hours * 3600
