import numpy as np
import pandas as pd


def add_indicators(frame, benchmark=None):
    df = frame.sort_index().copy()
    for period in (10, 20, 50, 200):
        df[f"ma{period}"] = df["close"].rolling(period).mean()
    previous_close = df["close"].shift(1)
    true_range = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - previous_close).abs(),
            (df["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    df["atr14"] = true_range.rolling(14).mean()
    df["avg_volume20"] = df["volume"].rolling(20).mean()
    df["avg_dollar_volume20"] = (df["close"] * df["volume"]).rolling(20).mean()
    df["prior_high20"] = df["high"].shift(1).rolling(20).max()
    df["prior_low20"] = df["low"].shift(1).rolling(20).min()
    df["return20"] = df["close"].pct_change(20)
    df["return60"] = df["close"].pct_change(60)
    up = df["close"] > previous_close
    df["up_volume20"] = df["volume"].where(up).rolling(20, min_periods=5).mean()
    df["down_volume20"] = df["volume"].where(~up).rolling(20, min_periods=5).mean()
    if benchmark is not None and not benchmark.empty:
        aligned = benchmark["close"].reindex(df.index).ffill()
        df["rs20"] = df["return20"] - aligned.pct_change(20)
        df["rs60"] = df["return60"] - aligned.pct_change(60)
    else:
        df["rs20"] = np.nan
        df["rs60"] = np.nan
    return df


def swing_points(df, window=5):
    size = window * 2 + 1
    highs = df["high"].eq(df["high"].rolling(size, center=True).max())
    lows = df["low"].eq(df["low"].rolling(size, center=True).min())
    return df.index[highs.fillna(False)], df.index[lows.fillna(False)]

