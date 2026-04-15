from __future__ import annotations

from typing import Any

from api_client import CurrencyApiError, fetch_currency_rates
from storage import StorageError, is_cache_fresh, read_from_file, save_to_file

TARGET_CURRENCIES = ["RUB", "EUR", "GBP"]


def _available_codes(data: dict[str, Any]) -> set[str]:
    rates = data.get("rates", {})
    base = data.get("base_code", "")
    if not isinstance(rates, dict):
        raise ValueError("В ответе нет словаря курсов валют.")
    codes = {str(code).upper() for code in rates.keys()}
    if isinstance(base, str) and base:
        codes.add(base.upper())
    return codes


def _validate_currency_code(code: str, available_codes: set[str]) -> str:
    normalized = code.strip().upper()
    if normalized not in available_codes:
        sample_codes = ", ".join(sorted(available_codes)[:20])
        raise ValueError(
            f"Код валюты '{normalized}' не найден. Доступные коды (первые 20): {sample_codes}"
        )
    return normalized


def convert_amount(data: dict[str, Any], from_currency: str, to_currency: str, amount: float) -> float:
    rates: dict[str, Any] = data.get("rates", {})
    if not isinstance(rates, dict):
        raise ValueError("В ответе нет словаря курсов валют.")

    available_codes = _available_codes(data)
    source = _validate_currency_code(from_currency, available_codes)
    target = _validate_currency_code(to_currency, available_codes)

    source_rate = 1.0 if source == data.get("base_code", "").upper() else rates.get(source)
    target_rate = 1.0 if target == data.get("base_code", "").upper() else rates.get(target)
    if source_rate in (None, 0):
        raise ValueError(f"Нет корректного курса для валюты {source}.")
    if target_rate is None:
        raise ValueError(f"Нет корректного курса для валюты {target}.")

    amount_in_base = amount / float(source_rate)
    return amount_in_base * float(target_rate)


def get_rates_with_cache(base_currency: str, path: str = "currency_rate.json") -> tuple[dict[str, Any], bool]:
    base = base_currency.strip().upper()
    if is_cache_fresh(path):
        try:
            cached = read_from_file(path)
            if cached.get("base_code") == base and isinstance(cached.get("rates"), dict):
                return cached, True
        except StorageError:
            # Corrupted cache should not block fresh API fetch.
            pass

    fresh = fetch_currency_rates(base)
    save_to_file(fresh, path=path)
    return fresh, False


def print_selected_rates(data: dict[str, Any], targets: list[str]) -> None:
    rates: dict[str, Any] = data.get("rates", {})
    base = data.get("base_code", "N/A")
    print(f"\nБазовая валюта: {base}")
    for code in targets:
        value = rates.get(code)
        if value is None:
            print(f"{code}: нет данных")
        else:
            print(f"{code}: {value}")


def run_cli() -> None:
    try:
        base_currency = input("Введите базовую валюту (например, USD): ").strip().upper()
        if not base_currency:
            raise ValueError("Базовая валюта не указана.")

        data, from_cache = get_rates_with_cache(base_currency)
        print("Использован кэш из currency_rate.json (моложе 24 часов)." if from_cache else "Данные обновлены из API и сохранены в currency_rate.json.")
        print_selected_rates(data, TARGET_CURRENCIES)

        available_codes = _available_codes(data)
        print("\nКонвертер суммы")
        from_currency = _validate_currency_code(input("Из валюты: "), available_codes)
        to_currency = _validate_currency_code(input("В валюту: "), available_codes)

        amount_text = input("Сумма: ").strip().replace(",", ".")
        amount = float(amount_text)
        if amount < 0:
            raise ValueError("Сумма не может быть отрицательной.")

        converted = convert_amount(data, from_currency, to_currency, amount)
        print(f"{amount:.4f} {from_currency} = {converted:.4f} {to_currency}")
    except (ValueError, CurrencyApiError, StorageError) as error:
        print(f"Ошибка: {error}")
