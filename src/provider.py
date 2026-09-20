from pathlib import Path
import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ["open", "high", "low", "close", "volume"]


def _normalize(frame):
    df = frame.rename(columns=lambda value: str(value).lower().replace(" ", "_"))
    if "adj_close" in df and "close" not in df:
        df["close"] = df["adj_close"]
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Missing price columns: {sorted(missing)}")
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[REQUIRED_COLUMNS].dropna().sort_index()


def download_prices(symbols, period="2y"):
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("Install dependencies with: pip install -r requirements.txt") from exc
    result = {}
    for symbol in symbols:
        frame = yf.download(symbol, period=period, auto_adjust=True, progress=False)
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        if not frame.empty:
            result[symbol] = _normalize(frame)
    return result


def generate_demo_prices(symbols, days=520, seed=42):
    """Generate deterministic OHLCV data so the UI can be reviewed offline."""
    result = {}
    dates = pd.bdate_range(end=pd.Timestamp.today().normalize(), periods=days)
    for offset, symbol in enumerate(symbols):
        rng = np.random.default_rng(seed + offset)
        drift = 0.00045 if offset % 3 else -0.0001
        returns = rng.normal(drift, 0.018, days)
        close = (80 + offset * 7) * np.exp(np.cumsum(returns))
        open_ = close * (1 + rng.normal(0, 0.004, days))
        spread = rng.uniform(0.004, 0.025, days)
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = rng.integers(2_000_000, 25_000_000, days).astype(float)
        volume[-1] *= 2.2
        result[symbol] = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=dates,
        )
    return result


def save_price_cache(prices, directory):
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    for symbol, frame in prices.items():
        frame.to_pickle(target / f"{symbol}.pkl")


def load_price_cache(directory):
    result = {}
    for path in Path(directory).glob("*.pkl"):
        result[path.stem] = _normalize(pd.read_pickle(path))
    return result

