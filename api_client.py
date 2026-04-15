from __future__ import annotations

from typing import Any

import requests


class CurrencyApiError(RuntimeError):
    """Raised when currency API request or response is invalid."""


def fetch_currency_rates(base_currency: str, timeout: int = 30) -> dict[str, Any]:
    base = base_currency.strip().upper()
    if not base:
        raise ValueError("Базовая валюта не указана.")

    url = f"https://open.er-api.com/v6/latest/{base}"
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as error:
        raise CurrencyApiError("Ошибка сети при запросе курсов валют.") from error

    if response.status_code != 200:
        raise CurrencyApiError(
            f"Не удалось получить курсы для {base}. HTTP {response.status_code}: {response.reason}"
        )

    try:
        data = response.json()
    except ValueError as error:
        raise CurrencyApiError("API вернул некорректный JSON.") from error

    if data.get("result") != "success":
        raise CurrencyApiError(
            f"API вернул ошибку для {base}: {data.get('error-type', 'unknown')}"
        )
    if not isinstance(data.get("rates"), dict):
        raise CurrencyApiError("Ответ API не содержит корректного списка курсов.")

    return data
