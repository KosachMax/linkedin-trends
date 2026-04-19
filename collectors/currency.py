"""
Currency collector — курсы валют через API ЦБ РФ.
"""
import json
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from pathlib import Path

import requests

HISTORY_FILE = Path("data/currency_history.json")

# CharCode → key
CBR_CODES = {"USD": "USDRUB", "EUR": "EURRUB", "CNY": "CNYRUB", "GBP": "GBPRUB"}

DISPLAY = {
    "USDRUB": {"label": "🇺🇸 USD/RUB", "suffix": "₽"},
    "EURRUB": {"label": "🇪🇺 EUR/RUB", "suffix": "₽"},
    "CNYRUB": {"label": "🇨🇳 CNY/RUB", "suffix": "₽"},
    "GBPRUB": {"label": "🇬🇧 GBP/RUB", "suffix": "₽"},
    "EURUSD": {"label": "💶 EUR/USD", "suffix": "$"},
}


def _load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_history(history: dict) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    sorted_dates = sorted(history.keys())[-30:]
    trimmed = {d: history[d] for d in sorted_dates}
    HISTORY_FILE.write_text(json.dumps(trimmed, indent=2, ensure_ascii=False), encoding="utf-8")


def _fetch_cbr(day: date) -> dict:
    date_str = day.strftime("%d/%m/%Y")
    url = f"https://www.cbr.ru/scripts/XML_daily.asp?date_req={date_str}"
    try:
        resp = requests.get(url, timeout=10)
        resp.encoding = "windows-1251"
        root = ET.fromstring(resp.text)
    except Exception as e:
        print(f"  [currency] CBR fetch error: {e}")
        return {}

    rates = {}
    for valute in root.findall("Valute"):
        code = valute.findtext("CharCode", "")
        key = CBR_CODES.get(code)
        if not key:
            continue
        nominal_text = valute.findtext("Nominal", "1").replace(",", ".")
        value_text = valute.findtext("Value", "").replace(",", ".")
        try:
            nominal = float(nominal_text)
            value = float(value_text)
            rates[key] = round(value / nominal, 4)
            print(f"  [currency] {key}: {rates[key]}")
        except ValueError:
            pass

    # Derived EURUSD
    if "EURRUB" in rates and "USDRUB" in rates and rates["USDRUB"] > 0:
        rates["EURUSD"] = round(rates["EURRUB"] / rates["USDRUB"], 4)
        print(f"  [currency] EURUSD: {rates['EURUSD']}")

    return rates


def fetch_and_save_rates() -> dict:
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    history = _load_history()

    rates = _fetch_cbr(today)
    if not rates:
        # Weekend fallback: try up to 3 days back
        for delta in range(1, 4):
            rates = _fetch_cbr(today - timedelta(days=delta))
            if rates:
                break

    if rates:
        history[today_str] = rates
        _save_history(history)

    return history


def get_rates_with_delta() -> dict:
    history = _load_history()
    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_rates = history.get(today, {})
    yesterday_rates = history.get(yesterday, {})

    if not today_rates and history:
        last_day = sorted(history.keys())[-1]
        today_rates = history[last_day]

    result = {}
    for key, display in DISPLAY.items():
        rate = today_rates.get(key)
        if rate is None:
            result[key] = {**display, "rate": None, "delta": None, "arrow": "—", "pct": "—", "delta_str": "—"}
            continue

        prev = yesterday_rates.get(key)
        if prev:
            delta = round(rate - prev, 4)
            pct = round((delta / prev) * 100, 1)
            sign = "+" if delta >= 0 else ""
            arrow = "↑" if delta > 0 else "↓" if delta < 0 else "→"
            result[key] = {
                **display,
                "rate": rate,
                "delta": delta,
                "arrow": arrow,
                "pct": f"{sign}{pct}%",
                "delta_str": f"{sign}{delta:.2f}",
            }
        else:
            result[key] = {**display, "rate": rate, "delta": None, "arrow": "—", "pct": "—", "delta_str": "—"}

    return result
