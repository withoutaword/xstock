from pathlib import Path
import pandas as pd

from .database import Database
from .edges import build_scan_result, evaluate_edges
from .indicators import add_indicators
from .provider import download_prices, generate_demo_prices, save_price_cache
from .watchlist import load_watchlist


def load_universe(settings):
    path = settings["root"] / settings["universe"]["file"]
    base = pd.read_csv(path)
    tracked = load_watchlist(settings["root"] / "config" / "watchlist.csv")
    return pd.concat([base, tracked], ignore_index=True).drop_duplicates("symbol", keep="first")


def analyze_symbols(settings, symbols, demo=False, persist=True):
    """Analyze an explicit symbol list for the on-demand query page."""
    symbols = list(dict.fromkeys(symbols))
    benchmark_symbol = settings["universe"]["benchmark"]
    request_symbols = symbols + ([benchmark_symbol] if benchmark_symbol not in symbols else [])
    prices = (
        generate_demo_prices(request_symbols)
        if demo else download_prices(request_symbols, settings["universe"]["history_period"])
    )
    if benchmark_symbol not in prices:
        raise RuntimeError(f"Benchmark {benchmark_symbol} has no data")
    benchmark = prices[benchmark_symbol]
    if persist:
        save_price_cache(prices, settings["root"] / "data" / "prices")
    results, errors = [], []
    db = Database(settings["root"] / "data" / "scanner.sqlite") if persist else None
    try:
        for symbol in symbols:
            try:
                if symbol not in prices:
                    raise ValueError("行情接口没有返回数据，请检查股票代码")
                featured = add_indicators(prices[symbol], benchmark)
                if len(featured) < 220:
                    raise ValueError(f"历史数据不足：仅 {len(featured)} 个交易日")
                edges = evaluate_edges(featured, settings)
                result = build_scan_result(symbol, featured, edges, settings)
                results.append(result)
                if db:
                    db.save_result(result)
            except Exception as exc:
                errors.append(f"{symbol}: {exc}")
    finally:
        if db:
            db.close()
    return results, errors


def run_scan(settings, demo=False):
    universe = load_universe(settings)
    symbols = universe["symbol"].drop_duplicates().tolist()
    benchmark_symbol = settings["universe"]["benchmark"]
    request_symbols = symbols + ([benchmark_symbol] if benchmark_symbol not in symbols else [])
    prices = (
        generate_demo_prices(request_symbols)
        if demo else download_prices(request_symbols, settings["universe"]["history_period"])
    )
    if benchmark_symbol not in prices:
        raise RuntimeError(f"Benchmark {benchmark_symbol} has no data")
    benchmark = prices[benchmark_symbol]
    cache_dir = settings["root"] / "data" / "prices"
    save_price_cache(prices, cache_dir)
    scan_date = str(max(frame.index.max() for frame in prices.values()).date())
    db = Database(settings["root"] / "data" / "scanner.sqlite")
    mode = "DEMO" if demo else "LIVE"
    db.start_run(scan_date, mode, len(symbols))
    db.clear_scan_date(scan_date)
    errors = []
    succeeded = 0
    try:
        for symbol in symbols:
            try:
                if symbol not in prices:
                    raise ValueError("No price data")
                featured = add_indicators(prices[symbol], benchmark)
                last = featured.iloc[-1]
                if last.close < settings["scan"]["minimum_price"]:
                    continue
                if last.avg_dollar_volume20 < settings["scan"]["minimum_avg_dollar_volume"]:
                    continue
                edges = evaluate_edges(featured, settings)
                result = build_scan_result(symbol, featured, edges, settings)
                db.save_result(result)
                succeeded += 1
            except Exception as exc:  # isolate single-symbol data failures
                errors.append(f"{symbol}: {exc}")
        db.finish_run(scan_date, mode, succeeded, errors)
    finally:
        db.close()
    return {"scan_date": scan_date, "succeeded": succeeded, "errors": errors, "mode": mode}
