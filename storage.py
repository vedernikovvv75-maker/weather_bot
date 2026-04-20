from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DATA_PATH = Path("User_Data.json")


def _read_all() -> dict[str, Any]:
    if not DATA_PATH.exists():
        return {}
    try:
        with DATA_PATH.open("r", encoding="utf-8") as file:
            data = json.load(file)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_all(data: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with DATA_PATH.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
    except OSError:
        return


def load_user(user_id: int) -> dict[str, Any]:
    all_data = _read_all()
    raw = all_data.get(str(user_id), {})
    if not isinstance(raw, dict):
        raw = {}

    notifications = raw.get("notifications", {})
    if not isinstance(notifications, dict):
        notifications = {}

    return {
        "city": raw.get("city"),
        "lat": raw.get("lat"),
        "lon": raw.get("lon"),
        "notifications": {
            "enabled": bool(notifications.get("enabled", False)),
            "interval_h": int(notifications.get("interval_h", 2) or 2),
        },
        "last_sent_at": raw.get("last_sent_at"),
    }


def save_user(user_id: int, data: dict[str, Any]) -> None:
    all_data = _read_all()
    all_data[str(user_id)] = {
        "city": data.get("city"),
        "lat": data.get("lat"),
        "lon": data.get("lon"),
        "notifications": data.get("notifications", {"enabled": False, "interval_h": 2}),
        "last_sent_at": data.get("last_sent_at"),
    }
    _write_all(all_data)
