import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY")
GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
CURRENT_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
CACHE_FILE = Path(__file__).resolve().parent / "weather_cache.json"
CACHE_MAX_AGE = timedelta(hours=3)
RETRY_DELAYS_SECONDS = (1, 2, 4)
REQUEST_TIMEOUT_SECONDS = 10


def make_request_with_retry(url: str, params: dict) -> Optional[requests.Response]:
    for attempt, delay in enumerate(RETRY_DELAYS_SECONDS, start=1):
        try:
            response = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SECONDS)
            if response.status_code != 429:
                return response
            print(f"Сервер временно ограничил запросы (429). Повтор через {delay} сек.")
            time.sleep(delay)
        except requests.RequestException as exc:
            if attempt == len(RETRY_DELAYS_SECONDS):
                print(f"Сетевая ошибка: {exc}")
                return None
            print(f"Временная сетевая ошибка. Повтор через {delay} сек.")
            time.sleep(delay)
    return None


def parse_api_error_message(response: requests.Response) -> str:
    default_message = "Неизвестная ошибка API."
    try:
        payload = response.json()
    except ValueError:
        return default_message
    if not isinstance(payload, dict):
        return default_message
    message = payload.get("message")
    return str(message) if message else default_message


def get_coordinates(city: str) -> Optional[tuple[float, float]]:
    if not API_KEY:
        print("API-ключ не найден. Заполните API_KEY в файле .env.")
        return None

    params = {"q": city, "limit": 1, "appid": API_KEY, "lang": "ru"}
    response = make_request_with_retry(GEOCODING_URL, params)
    if response is None:
        return None

    if response.status_code != 200:
        message = parse_api_error_message(response)
        print(f"Ошибка геокодинга ({response.status_code}): {message}")
        return None

    locations = response.json()
    if not locations:
        print(f"Город '{city}' не найден.")
        return None

    latitude = locations[0].get("lat")
    longitude = locations[0].get("lon")
    if latitude is None or longitude is None:
        print("Не удалось получить координаты из ответа API.")
        return None
    return float(latitude), float(longitude)


def get_weather_by_coordinates(lat: float, lon: float) -> Optional[dict]:
    if not API_KEY:
        print("API-ключ не найден. Заполните API_KEY в файле .env.")
        return None

    params = {"lat": lat, "lon": lon, "appid": API_KEY, "units": "metric", "lang": "ru"}
    response = make_request_with_retry(CURRENT_WEATHER_URL, params)
    if response is None:
        return None

    if response.status_code != 200:
        message = parse_api_error_message(response)
        if response.status_code == 401:
            print("Невалидный API-ключ OpenWeather. Проверьте API_KEY в .env.")
        else:
            print(f"Ошибка получения погоды ({response.status_code}): {message}")
        return None

    return response.json()


def save_cache(city: Optional[str], lat: float, lon: float, weather_data: dict) -> None:
    payload = {
        "city": city,
        "lat": lat,
        "lon": lon,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "weather": weather_data,
    }
    try:
        CACHE_FILE.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"Не удалось сохранить кэш: {exc}")


def load_cache_if_fresh() -> Optional[dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        fetched_at = datetime.fromisoformat(payload["fetched_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None

    if datetime.now(timezone.utc) - fetched_at > CACHE_MAX_AGE:
        return None
    return payload


def get_current_weather(
    city: str = None,
    latitude: float = None,
    longitude: float = None,
) -> Optional[dict]:
    if city:
        coordinates = get_coordinates(city)
        if coordinates is None:
            return None
        latitude, longitude = coordinates
    elif latitude is None or longitude is None:
        print("Передайте либо город, либо одновременно latitude и longitude.")
        return None

    weather = get_weather_by_coordinates(latitude, longitude)
    if weather is not None:
        save_cache(city, latitude, longitude, weather)
    return weather


def format_weather_line(weather_data: dict, fallback_city: Optional[str] = None) -> str:
    city_name = weather_data.get("name") or fallback_city or "неизвестный город"
    temperature = weather_data.get("main", {}).get("temp")
    description_list = weather_data.get("weather", [])
    description = (
        description_list[0].get("description")
        if description_list and isinstance(description_list[0], dict)
        else "нет описания"
    )
    if temperature is None:
        return f"Погода в {city_name}: нет данных о температуре, {description}"
    return f"Погода в {city_name}: {temperature}°C, {description}"


def maybe_offer_cache() -> Optional[dict]:
    cached = load_cache_if_fresh()
    if cached is None:
        return None

    decision = input("Нет свежего ответа от API. Показать данные из кэша? (y/n): ").strip().lower()
    if decision not in {"y", "yes", "д", "да"}:
        return None
    return cached


def ask_city() -> Optional[dict]:
    city = input("Введите название города: ").strip()
    if not city:
        print("Название города не может быть пустым.")
        return None

    weather = get_current_weather(city=city)
    if weather is not None:
        print(format_weather_line(weather, fallback_city=city))
        return weather

    cached = maybe_offer_cache()
    if cached is None:
        return None
    print(format_weather_line(cached["weather"], fallback_city=cached.get("city")))
    return cached["weather"]


def ask_coordinates() -> Optional[dict]:
    raw_lat = input("Введите широту: ").strip()
    raw_lon = input("Введите долготу: ").strip()

    try:
        lat = float(raw_lat)
        lon = float(raw_lon)
    except ValueError:
        print("Координаты должны быть числами.")
        return None

    weather = get_current_weather(latitude=lat, longitude=lon)
    if weather is not None:
        print(format_weather_line(weather))
        return weather

    cached = maybe_offer_cache()
    if cached is None:
        return None
    print(format_weather_line(cached["weather"], fallback_city=cached.get("city")))
    return cached["weather"]


def run_cli() -> None:
    print("Приложение погоды OpenWeather")
    while True:
        print("\nВыберите режим:")
        print("1 - По городу")
        print("2 - По координатам")
        print("0 - Выход")
        mode = input("Ваш выбор: ").strip()

        if mode == "0":
            print("Выход из приложения.")
            break
        if mode == "1":
            ask_city()
            continue
        if mode == "2":
            ask_coordinates()
            continue
        print("Неизвестная команда. Попробуйте снова.")


if __name__ == "__main__":
    run_cli()
