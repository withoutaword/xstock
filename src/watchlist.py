import re
from pathlib import Path
import pandas as pd


SYMBOL_PATTERN = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
COLUMNS = ["symbol", "name", "sector"]


def parse_symbols(value):
    """Parse comma/space/newline separated symbols and preserve order."""
    candidates = re.split(r"[\s,;，；]+", (value or "").upper().strip())
    result = []
    for symbol in candidates:
        if not symbol:
            continue
        if not SYMBOL_PATTERN.fullmatch(symbol):
            raise ValueError(f"无效股票代码：{symbol}")
        if symbol not in result:
            result.append(symbol)
    return result


def load_watchlist(path):
    target = Path(path)
    if not target.exists() or target.stat().st_size == 0:
        return pd.DataFrame(columns=COLUMNS)
    frame = pd.read_csv(target)
    for column in COLUMNS:
        if column not in frame:
            frame[column] = ""
    return frame[COLUMNS].dropna(subset=["symbol"])


def add_to_watchlist(path, symbols):
    target = Path(path)
    current = load_watchlist(target)
    additions = pd.DataFrame(
        [{"symbol": symbol, "name": symbol, "sector": "Custom"} for symbol in symbols]
    )
    merged = pd.concat([current, additions], ignore_index=True)
    merged["symbol"] = merged["symbol"].str.upper()
    merged = merged.drop_duplicates("symbol", keep="first").sort_values("symbol")
    target.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(target, index=False)
    return merged


def remove_from_watchlist(path, symbols):
    target = Path(path)
    current = load_watchlist(target)
    remaining = current[~current.symbol.isin(set(symbols))]
    remaining.to_csv(target, index=False)
    return remaining

