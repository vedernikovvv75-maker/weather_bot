from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OW_API_KEY", "").strip()
BASE_URL = "https://api.openweathermap.org"
CACHE_DIR = Path(".cache")
CACHE_TTL_SECONDS = 600
RETRY_DELAYS = (1, 2, 4)
REQUEST_TIMEOUT = 10

DESCRIPTION_TRANSLATIONS = {
    "clear sky": "ясно",
    "few clouds": "малооблачно",
    "scattered clouds": "рассеянные облака",
    "broken clouds": "облачно с прояснениями",
    "overcast clouds": "пасмурно",
    "mist": "туман",
    "haze": "мгла",
    "fog": "туман",
    "light rain": "небольшой дождь",
    "moderate rain": "умеренный дождь",
    "heavy intensity rain": "сильный дождь",
    "very heavy rain": "очень сильный дождь",
    "light snow": "небольшой снег",
    "snow": "снег",
    "thunderstorm": "гроза",
    "drizzle": "морось",
}

AIR_LABELS = {
    "pm2_5": "PM2.5",
    "pm10": "PM10",
    "no2": "NO2",
    "so2": "SO2",
    "o3": "O3",
    "co": "CO",
}


def _build_cache_key(endpoint: str, params: dict[str, Any]) -> str:
    lat = params.get("lat", "")
    lon = params.get("lon", "")
    suffix = json.dumps(params, sort_keys=True, ensure_ascii=True)
    raw = f"{endpoint}|{lat}|{lon}|{suffix}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / f"{key}.json"


def _read_cache(key: str) -> Any | None:
    path = _cache_path(key)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            wrapped = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    saved_at = wrapped.get("saved_at")
    if not isinstance(saved_at, (int, float)):
        return None
    if time.time() - float(saved_at) > CACHE_TTL_SECONDS:
        return None
    return wrapped.get("payload")


def _write_cache(key: str, payload: Any) -> None:
    wrapped = {"saved_at": time.time(), "payload": payload}
    try:
        with _cache_path(key).open("w", encoding="utf-8") as f:
            json.dump(wrapped, f, ensure_ascii=False, indent=2)
    except OSError:
        return


def _request_json(endpoint: str, params: dict[str, Any], use_cache: bool = True) -> dict[str, Any] | list[Any] | None:
    if not API_KEY:
        return None
    merged = dict(params)
    merged["appid"] = API_KEY
    cache_key = _build_cache_key(endpoint, merged)
    if use_cache:
        cached = _read_cache(cache_key)
        if cached is not None:
            return cached

    url = f"{BASE_URL}{endpoint}"
    for idx in range(len(RETRY_DELAYS) + 1):
        try:
            response = requests.get(url, params=merged, timeout=REQUEST_TIMEOUT)
        except requests.RequestException:
            if idx < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[idx])
                continue
            return None

        if response.status_code == 429:
            if idx < len(RETRY_DELAYS):
                time.sleep(RETRY_DELAYS[idx])
                continue
            return None

        if 400 <= response.status_code <= 599:
            return None

        try:
            payload = response.json()
        except ValueError:
            return None

        if use_cache:
            _write_cache(cache_key, payload)
        return payload
    return None


def _translate_weather(description: str) -> str:
    normalized = description.strip().lower()
    if not normalized:
        return "нет данных"
    return DESCRIPTION_TRANSLATIONS.get(normalized, description)


def get_coordinates(city: str, limit: int = 1) -> tuple[float, float] | None:
    city_clean = city.strip()
    if not city_clean:
        return None
    payload = _request_json("/geo/1.0/direct", {"q": city_clean, "limit": limit, "lang": "ru"})
    if not isinstance(payload, list) or not payload:
        return None
    first = payload[0]
    lat = first.get("lat")
    lon = first.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None
    return float(lat), float(lon)


def get_current_weather(lat: float, lon: float) -> dict[str, Any]:
    payload = _request_json("/data/2.5/weather", {"lat": lat, "lon": lon, "units": "metric", "lang": "ru"})
    if not isinstance(payload, dict):
        return {"ok": False, "message": "Не удалось получить текущую погоду."}
    weather = payload.get("weather") or []
    description = "нет данных"
    if isinstance(weather, list) and weather and isinstance(weather[0], dict):
        raw_description = weather[0].get("description", "")
        if isinstance(raw_description, str):
            description = _translate_weather(raw_description)
    main = payload.get("main") or {}
    wind = payload.get("wind") or {}
    return {
        "ok": True,
        "name": payload.get("name", "Неизвестно"),
        "temperature": main.get("temp"),
        "feels_like": main.get("feels_like"),
        "humidity": main.get("humidity"),
        "pressure": main.get("pressure"),
        "wind_speed": wind.get("speed"),
        "description": description,
        "raw": payload,
    }


def get_forecast_5d3h(lat: float, lon: float) -> list[dict[str, Any]]:
    payload = _request_json("/data/2.5/forecast", {"lat": lat, "lon": lon, "units": "metric", "lang": "ru"})
    if not isinstance(payload, dict):
        return []
    items = payload.get("list")
    if not isinstance(items, list):
        return []

    result: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        weather = item.get("weather") or []
        description = "нет данных"
        if isinstance(weather, list) and weather and isinstance(weather[0], dict):
            raw_description = weather[0].get("description", "")
            if isinstance(raw_description, str):
                description = _translate_weather(raw_description)
        main = item.get("main") or {}
        wind = item.get("wind") or {}
        result.append(
            {
                "dt": item.get("dt"),
                "dt_txt": item.get("dt_txt"),
                "temperature": main.get("temp"),
                "feels_like": main.get("feels_like"),
                "humidity": main.get("humidity"),
                "description": description,
                "wind_speed": wind.get("speed"),
            }
        )
    return result


def get_air_pollution(lat: float, lon: float) -> dict[str, Any]:
    payload = _request_json("/data/2.5/air_pollution", {"lat": lat, "lon": lon})
    if not isinstance(payload, dict):
        return {"ok": False, "message": "Не удалось получить данные о качестве воздуха."}
    rows = payload.get("list")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return {"ok": False, "message": "Данные о качестве воздуха отсутствуют."}
    first = rows[0]
    components = first.get("components")
    if not isinstance(components, dict):
        components = {}
    return {"ok": True, "aqi": (first.get("main") or {}).get("aqi"), "components": components}


def analyze_air_pollution(components: dict, extended: bool = False) -> dict[str, Any]:
    thresholds = {
        "pm2_5": (15, 35, 55),
        "pm10": (45, 100, 200),
        "no2": (50, 100, 200),
        "so2": (40, 80, 160),
        "o3": (100, 160, 240),
        "co": (4000, 9000, 15000),
    }
    total_score = 0
    details: dict[str, str] = {}
    for key, (low, medium, high) in thresholds.items():
        value_raw = components.get(key, 0) if isinstance(components, dict) else 0
        value = float(value_raw) if isinstance(value_raw, (int, float)) else 0.0
        if value <= low:
            score, label = 0, "низкий"
        elif value <= medium:
            score, label = 1, "умеренный"
        elif value <= high:
            score, label = 2, "повышенный"
        else:
            score, label = 3, "высокий"
        total_score += score
        details[AIR_LABELS.get(key, key)] = f"{value:g} мкг/м3 ({label})"

    avg = total_score / max(len(thresholds), 1)
    if avg <= 0.5:
        status = "Низкое загрязнение"
    elif avg <= 1.4:
        status = "Умеренное загрязнение"
    elif avg <= 2.2:
        status = "Повышенное загрязнение"
    else:
        status = "Высокое загрязнение"
    result: dict[str, Any] = {"status": status}
    if extended:
        result["details"] = details
    return result
