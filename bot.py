from __future__ import annotations

import os
import time
from collections import defaultdict
from datetime import datetime
from typing import Any

import telebot
from dotenv import load_dotenv
from telebot import types

from storage import load_user, save_user
from weather_app import (
    analyze_air_pollution,
    get_air_pollution,
    get_coordinates,
    get_current_weather,
    get_forecast_5d3h,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не найден в .env")

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")
user_states: dict[int, dict[str, Any]] = defaultdict(dict)
BOT_USERNAME = ""

MENU_CURRENT = "Текущая погода"
MENU_FORECAST = "Прогноз на 5 дней"
MENU_LOCATION = "Моя геолокация"
MENU_COMPARE = "Сравнить города"
MENU_EXTENDED = "Расширенные данные"
MENU_NOTIFY = "Уведомления"


def main_menu() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row(MENU_CURRENT, MENU_FORECAST)
    kb.row(MENU_LOCATION, MENU_COMPARE)
    kb.row(MENU_EXTENDED, MENU_NOTIFY)
    return kb


def location_menu() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(types.KeyboardButton("Отправить геолокацию", request_location=True))
    kb.add("Отмена")
    return kb


def _format_weather(data: dict[str, Any], title: str) -> str:
    if not data.get("ok"):
        return data.get("message", "Не удалось получить данные о погоде.")
    return (
        f"<b>{title}</b>\n"
        f"Город: {data.get('name')}\n"
        f"Описание: {data.get('description')}\n"
        f"Температура: {data.get('temperature')}°C\n"
        f"Ощущается как: {data.get('feels_like')}°C\n"
        f"Влажность: {data.get('humidity')}%\n"
        f"Давление: {data.get('pressure')} гПа\n"
        f"Ветер: {data.get('wind_speed')} м/с"
    )


def _save_user_location(user_id: int, lat: float, lon: float, city: str | None = None) -> None:
    user = load_user(user_id)
    user["lat"] = lat
    user["lon"] = lon
    if city:
        user["city"] = city
    save_user(user_id, user)


def _resolve_user_coords(user_id: int, city_text: str | None = None) -> tuple[float, float] | None:
    if city_text and city_text.strip():
        coords = get_coordinates(city_text.strip())
        if not coords:
            return None
        _save_user_location(user_id, coords[0], coords[1], city_text.strip())
        return coords

    user = load_user(user_id)
    lat, lon = user.get("lat"), user.get("lon")
    if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
        return float(lat), float(lon)
    return None


def _group_forecast_by_day(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        dt_txt = item.get("dt_txt")
        if isinstance(dt_txt, str) and len(dt_txt) >= 10:
            grouped.setdefault(dt_txt[:10], []).append(item)
    return grouped


def _render_day_details(day: str, items: list[dict[str, Any]]) -> str:
    lines = [f"<b>Прогноз на {day}</b>"]
    for item in items:
        dt_txt = item.get("dt_txt", "")
        hour = dt_txt[11:16] if isinstance(dt_txt, str) and len(dt_txt) >= 16 else "--:--"
        lines.append(
            f"{hour} | {item.get('temperature')}°C | {item.get('description')} | "
            f"ветер {item.get('wind_speed')} м/с"
        )
    return "\n".join(lines)


def _check_notifications(user_id: int, chat_id: int) -> None:
    user = load_user(user_id)
    notifications = user.get("notifications", {})
    if not isinstance(notifications, dict) or not notifications.get("enabled"):
        return

    interval_h = int(notifications.get("interval_h", 2) or 2)
    last_sent_at = user.get("last_sent_at")
    now = int(time.time())
    if isinstance(last_sent_at, (int, float)) and now - int(last_sent_at) < interval_h * 3600:
        return

    lat, lon = user.get("lat"), user.get("lon")
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return

    weather = get_current_weather(float(lat), float(lon))
    if weather.get("ok"):
        bot.send_message(chat_id, _format_weather(weather, "Уведомление о погоде"))
        user["last_sent_at"] = now
        save_user(user_id, user)


@bot.message_handler(commands=["start"])
def handle_start(message: types.Message) -> None:
    user = load_user(message.from_user.id)
    if "notifications" not in user:
        user["notifications"] = {"enabled": False, "interval_h": 2}
        save_user(message.from_user.id, user)
    bot.send_message(message.chat.id, "Выберите действие:", reply_markup=main_menu())


@bot.message_handler(content_types=["location"])
def handle_location(message: types.Message) -> None:
    user_id = message.from_user.id
    _check_notifications(user_id, message.chat.id)
    if not message.location:
        bot.send_message(message.chat.id, "Пустая геолокация. Пожалуйста, отправьте location.")
        return
    _save_user_location(user_id, message.location.latitude, message.location.longitude)
    bot.send_message(message.chat.id, "Геолокация сохранена.", reply_markup=main_menu())


@bot.callback_query_handler(func=lambda c: c.data.startswith("forecast_day:"))
def handle_forecast_day(call: types.CallbackQuery) -> None:
    state = user_states.get(call.from_user.id, {})
    grouped = state.get("forecast_grouped", {})
    day = call.data.split(":", 1)[1]
    if not isinstance(grouped, dict) or day not in grouped:
        bot.answer_callback_query(call.id, "Данные устарели, запросите прогноз снова.")
        return
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("Назад", callback_data="forecast_back"))
    bot.edit_message_text(_render_day_details(day, grouped[day]), call.message.chat.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.callback_query_handler(func=lambda c: c.data == "forecast_back")
def handle_forecast_back(call: types.CallbackQuery) -> None:
    state = user_states.get(call.from_user.id, {})
    grouped = state.get("forecast_grouped", {})
    if not isinstance(grouped, dict) or not grouped:
        bot.answer_callback_query(call.id, "Данные устарели, запросите прогноз снова.")
        return
    kb = types.InlineKeyboardMarkup()
    for day in grouped:
        kb.add(types.InlineKeyboardButton(datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y"), callback_data=f"forecast_day:{day}"))
    bot.edit_message_text("Выберите день прогноза:", call.message.chat.id, call.message.message_id, reply_markup=kb)
    bot.answer_callback_query(call.id)


@bot.message_handler(func=lambda m: True, content_types=["text"])
def handle_text(message: types.Message) -> None:
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = (message.text or "").strip()
    state = user_states.get(user_id, {}).get("state")

    _check_notifications(user_id, chat_id)

    if text == MENU_CURRENT:
        user_states[user_id] = {"state": "await_current_city"}
        bot.send_message(chat_id, "Введите город или отправьте геолокацию кнопкой «Моя геолокация».")
        return
    if text == MENU_FORECAST:
        user_states[user_id] = {"state": "await_forecast_city"}
        bot.send_message(chat_id, "Введите город для прогноза на 5 дней.")
        return
    if text == MENU_LOCATION:
        bot.send_message(chat_id, "Отправьте вашу геолокацию:", reply_markup=location_menu())
        return
    if text == MENU_COMPARE:
        user_states[user_id] = {"state": "await_compare_city_1"}
        bot.send_message(chat_id, "Введите первый город для сравнения.")
        return
    if text == MENU_EXTENDED:
        user_states[user_id] = {"state": "await_extended_city"}
        bot.send_message(chat_id, "Введите город для расширенных данных.")
        return
    if text == MENU_NOTIFY:
        user = load_user(user_id)
        notifications = user.get("notifications", {"enabled": False, "interval_h": 2})
        enabled = "включены" if notifications.get("enabled") else "выключены"
        bot.send_message(
            chat_id,
            f"Уведомления сейчас {enabled}. Интервал: {notifications.get('interval_h', 2)} ч.\n"
            "Команды: notify on | notify off | notify <часы>",
        )
        user_states[user_id] = {"state": "await_notify"}
        return
    if text.lower() == "отмена":
        user_states[user_id] = {}
        bot.send_message(chat_id, "Отменено.", reply_markup=main_menu())
        return

    if state == "await_current_city":
        coords = _resolve_user_coords(user_id, text if text else None)
        if not coords:
            bot.send_message(chat_id, "Город не найден")
            return
        bot.send_message(chat_id, _format_weather(get_current_weather(coords[0], coords[1]), "Текущая погода"), reply_markup=main_menu())
        user_states[user_id] = {}
        return

    if state == "await_forecast_city":
        coords = _resolve_user_coords(user_id, text)
        if not coords:
            bot.send_message(chat_id, "Город не найден")
            return
        grouped = _group_forecast_by_day(get_forecast_5d3h(coords[0], coords[1]))
        if not grouped:
            bot.send_message(chat_id, "Не удалось получить прогноз.")
            return
        user_states[user_id] = {"state": "forecast_days", "forecast_grouped": grouped}
        kb = types.InlineKeyboardMarkup()
        for day in grouped:
            kb.add(types.InlineKeyboardButton(datetime.strptime(day, "%Y-%m-%d").strftime("%d.%m.%Y"), callback_data=f"forecast_day:{day}"))
        bot.send_message(chat_id, "Выберите день прогноза:", reply_markup=kb)
        return

    if state == "await_compare_city_1":
        coords1 = get_coordinates(text)
        if not coords1:
            bot.send_message(chat_id, "Город не найден")
            return
        user_states[user_id] = {"state": "await_compare_city_2", "city1": text, "coords1": coords1}
        bot.send_message(chat_id, "Введите второй город.")
        return

    if state == "await_compare_city_2":
        coords2 = get_coordinates(text)
        if not coords2:
            bot.send_message(chat_id, "Город не найден")
            return
        city1 = user_states[user_id]["city1"]
        coords1 = user_states[user_id]["coords1"]
        w1 = get_current_weather(coords1[0], coords1[1])
        w2 = get_current_weather(coords2[0], coords2[1])
        if not w1.get("ok") or not w2.get("ok"):
            bot.send_message(chat_id, "Не удалось сравнить города.")
            user_states[user_id] = {}
            return
        bot.send_message(
            chat_id,
            "<b>Сравнение городов</b>\n"
            "Город | Температура | Описание\n"
            f"{city1} | {w1.get('temperature')}°C | {w1.get('description')}\n"
            f"{text} | {w2.get('temperature')}°C | {w2.get('description')}",
            reply_markup=main_menu(),
        )
        user_states[user_id] = {}
        return

    if state == "await_extended_city":
        coords = _resolve_user_coords(user_id, text)
        if not coords:
            bot.send_message(chat_id, "Город не найден")
            return
        weather = get_current_weather(coords[0], coords[1])
        air = get_air_pollution(coords[0], coords[1])
        if not weather.get("ok"):
            bot.send_message(chat_id, "Не удалось получить расширенные данные.")
            return
        analysis = analyze_air_pollution(air.get("components", {}), extended=True) if air.get("ok") else {"status": "Нет данных", "details": {}}
        detail_rows = analysis.get("details", {})
        detail_text = "\n".join([f"- {k}: {v}" for k, v in detail_rows.items()]) if detail_rows else "нет данных"
        bot.send_message(
            chat_id,
            f"{_format_weather(weather, 'Расширенные данные')}\n\n"
            f"<b>Качество воздуха</b>\nСтатус: {analysis.get('status')}\n{detail_text}",
            reply_markup=main_menu(),
        )
        user_states[user_id] = {}
        return

    if state == "await_notify":
        user = load_user(user_id)
        notifications = user.get("notifications", {"enabled": False, "interval_h": 2})
        lower = text.lower()
        if lower == "notify on":
            notifications["enabled"] = True
        elif lower == "notify off":
            notifications["enabled"] = False
        elif lower.startswith("notify "):
            parts = lower.split()
            if len(parts) == 2 and parts[1].isdigit() and 1 <= int(parts[1]) <= 24:
                notifications["interval_h"] = int(parts[1])
            else:
                bot.send_message(chat_id, "Некорректный интервал. Укажите от 1 до 24 часов.")
                return
        else:
            bot.send_message(chat_id, "Некорректная команда. Примеры: notify on | notify off | notify 2")
            return
        user["notifications"] = notifications
        save_user(user_id, user)
        user_states[user_id] = {}
        bot.send_message(chat_id, "Настройки уведомлений обновлены.", reply_markup=main_menu())
        return

    bot.send_message(chat_id, "Выберите действие через меню или /start.", reply_markup=main_menu())


@bot.inline_handler(func=lambda q: True)
def inline_weather(inline_query: types.InlineQuery) -> None:
    query = (inline_query.query or "").strip()
    if not query:
        return

    coords = get_coordinates(query)
    if not coords:
        result = types.InlineQueryResultArticle(
            id="not_found",
            title="Город не найден",
            description="Попробуйте другое название города",
            input_message_content=types.InputTextMessageContent("Город не найден"),
        )
        bot.answer_inline_query(inline_query.id, [result], cache_time=5)
        return

    weather = get_current_weather(coords[0], coords[1])
    if not weather.get("ok"):
        return

    forecast_link = f"https://t.me/{BOT_USERNAME}" if BOT_USERNAME else "Откройте бота для прогноза"
    message_text = (
        f"Температура: {weather.get('temperature')}°C\n"
        f"Описание: {weather.get('description')}\n"
        f"Прогноз: {forecast_link}"
    )
    result = types.InlineQueryResultArticle(
        id=f"weather_{query.lower()}",
        title=f"{query}: {weather.get('temperature')}°C, {weather.get('description')}",
        description="Текущая погода",
        input_message_content=types.InputTextMessageContent(message_text),
    )
    bot.answer_inline_query(inline_query.id, [result], cache_time=60)


if __name__ == "__main__":
    try:
        BOT_USERNAME = bot.get_me().username or ""
    except Exception:
        BOT_USERNAME = ""
    bot.infinity_polling(skip_pending=True, timeout=30, long_polling_timeout=30)
