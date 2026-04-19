"""
Currency collector — курсы валют через yfinance с историей изменений.
"""
import json
from datetime import date, timedelta
from pathlib import Path

PAIRS = {
    "USDRUB": "USDRUB=X",
    "EURRUB": "EURRUB=X",
    "CNYRUB": "CNYRUB=X",
    "GBPRUB": "GBPRUB=X",
    "EURUSD": "EURUSD=X",
}

HISTORY_FILE = Path("data/currency_history.json")

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


def fetch_and_save_rates() -> dict:
    today = date.today().strftime("%Y-%m-%d")
    history = _load_history()

    try:
        import yfinance as yf
        rates = {}
        for key, ticker in PAIRS.items():
            try:
                data = yf.download(ticker, period="2d", interval="1d", progress=False, auto_adjust=True)
                if not data.empty:
                    rates[key] = round(float(data["Close"].iloc[-1]), 4)
                    print(f"  [currency] {key}: {rates[key]}")
            except Exception as e:
                print(f"  [currency] Ошибка {key}: {e}")

        if rates:
            history[today] = rates
            _save_history(history)
    except ImportError:
        print("  [currency] yfinance не установлен — пропускаю")
    except Exception as e:
        print(f"  [currency] Ошибка загрузки: {e}")

    return history


def get_rates_with_delta() -> dict:
    history = _load_history()
    today = date.today().strftime("%Y-%m-%d")
    yesterday = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")

    today_rates = history.get(today, {})
    yesterday_rates = history.get(yesterday, {})

    # Fallback: use last available day if today missing
    if not today_rates and history:
        last_day = sorted(history.keys())[-1]
        today_rates = history[last_day]

    result = {}
    for key in PAIRS:
        display = DISPLAY[key]
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
            result[key] = {
                **display,
                "rate": rate,
                "delta": None,
                "arrow": "—",
                "pct": "—",
                "delta_str": "—",
            }

    return result
