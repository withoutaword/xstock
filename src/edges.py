import math
from .indicators import swing_points
from .models import ChartMarker, EdgeResult, ScanResult


CATEGORY_CAPS = {
    "TREND": 25,
    "VOLUME": 20,
    "MA": 15,
    "STRUCTURE": 20,
    "KEY_LEVEL": 10,
    "TRIGGER": 10,
}


def _edge(code, name, direction, category, active, strength, explanation, row, status=None, raw=None):
    strength = max(0.0, min(float(strength), 1.0))
    if status is None:
        status = "ACTIVE" if active and strength >= 0.75 else "PARTIAL" if active else "INACTIVE"
    score = CATEGORY_CAPS[category] * strength if status in {"ACTIVE", "CONFIRMED", "PARTIAL"} else 0.0
    markers = []
    if active:
        markers.append(ChartMarker(str(row.name.date()), float(row["close"]), code))
    return EdgeResult(
        code, name, direction, category, status, strength, score, explanation,
        raw or {}, markers,
    )


def _weighted_strength(conditions):
    """Return 0..1 and a human-readable pass/fail summary.

    conditions is an iterable of (label, passed, weight). Keeping the atomic
    evidence here prevents one weak sub-condition from erasing an entire Edge.
    """
    total = sum(weight for _, _, weight in conditions)
    achieved = sum(weight for _, passed, weight in conditions if passed)
    strength = achieved / total if total else 0.0
    summary = "；".join(("✓ " if passed else "✗ ") + label for label, passed, _ in conditions)
    raw = {label: bool(passed) for label, passed, _ in conditions}
    return strength, summary, raw


def evaluate_edges(df, settings):
    if len(df) < 220:
        return []
    row = df.iloc[-1]
    prev = df.iloc[-2]
    near_pct = settings["edges"]["near_ma_pct"]
    expansion = settings["edges"]["volume_expansion"]
    contraction = settings["edges"]["volume_contraction"]
    high_dates, low_dates = swing_points(df, settings["edges"]["swing_window"])
    recent_highs = df.loc[high_dates, "high"].tail(2)
    recent_lows = df.loc[low_dates, "low"].tail(2)
    higher_high = len(recent_highs) == 2 and recent_highs.iloc[-1] > recent_highs.iloc[-2]
    higher_low = len(recent_lows) == 2 and recent_lows.iloc[-1] > recent_lows.iloc[-2]
    lower_high = len(recent_highs) == 2 and recent_highs.iloc[-1] < recent_highs.iloc[-2]
    lower_low = len(recent_lows) == 2 and recent_lows.iloc[-1] < recent_lows.iloc[-2]
    edges = []

    l1_conditions = [
        ("价格高于MA50和MA200", row.close > row.ma50 > row.ma200, 25),
        ("MA20斜率向上", row.ma20 > df.ma20.iloc[-11], 15),
        ("MA50斜率向上", row.ma50 > df.ma50.iloc[-21], 15),
        ("Higher High", higher_high, 20),
        ("Higher Low", higher_low, 20),
        ("60日跑赢基准", row.rs60 > 0 if not math.isnan(row.rs60) else False, 5),
    ]
    l1_strength, l1_summary, l1_raw = _weighted_strength(l1_conditions)
    edges.append(_edge("L1", "强劲上升趋势", "LONG", "TREND", l1_strength >= 0.55, l1_strength,
        l1_summary, row, raw=l1_raw))

    pullback = row.close / df.high.iloc[-21:-1].max() - 1
    l2_conditions = [
        ("上涨日平均量不低于下跌日", row.up_volume20 >= row.down_volume20, 30),
        ("上涨/下跌平均量比至少1.15", row.up_volume20 >= row.down_volume20 * 1.15, 20),
        ("处于2%至15%回调", -0.15 <= pullback <= -0.02, 20),
        ("近10日量低于50日均量", df.volume.iloc[-10:].mean() < df.volume.iloc[-50:].mean() * 0.9, 20),
        ("价格仍在MA50上方", row.close > row.ma50, 10),
    ]
    l2_strength, l2_summary, l2_raw = _weighted_strength(l2_conditions)
    edges.append(_edge("L2", "上涨放量、回调缩量", "LONG", "VOLUME", l2_strength >= 0.5, l2_strength,
        f"{l2_summary}；上涨/下跌量比={row.up_volume20 / row.down_volume20:.2f}，回调={pullback:.1%}。", row, raw=l2_raw))

    prior_gain = df.close.iloc[-11] / df.close.iloc[-41] - 1
    l3_conditions = [
        ("前段涨幅至少10%", prior_gain >= 0.10, 25),
        ("前段涨幅至少15%", prior_gain >= 0.15, 15),
        ("回撤处于2%至15%", -0.15 <= pullback <= -0.02, 25),
        ("整理期量能收缩", df.volume.iloc[-10:].mean() < df.volume.iloc[-50:].mean() * 0.9, 20),
        ("价格位于MA50上方", row.close > row.ma50, 15),
    ]
    l3_strength, l3_summary, l3_raw = _weighted_strength(l3_conditions)
    edges.append(_edge("L3", "旗形整理（实验）", "LONG", "STRUCTURE", l3_strength >= 0.6, l3_strength * 0.8,
        f"{l3_summary}；前段涨幅={prior_gain:.1%}，当前回撤={pullback:.1%}。", row, raw=l3_raw))

    l4_conditions = [
        ("价格高于MA10", row.close > row.ma10, 10), ("价格高于MA20", row.close > row.ma20, 10),
        ("价格高于MA50", row.close > row.ma50, 15), ("MA10>MA20>MA50", row.ma10 > row.ma20 > row.ma50, 20),
        ("MA10向上", row.ma10 > df.ma10.iloc[-6], 15), ("MA20向上", row.ma20 > df.ma20.iloc[-11], 15),
        ("MA50向上", row.ma50 > df.ma50.iloc[-21], 15),
    ]
    l4_strength, l4_summary, l4_raw = _weighted_strength(l4_conditions)
    edges.append(_edge("L4", "10/20/50日线向上且低于股价", "LONG", "MA", l4_strength >= 0.5, l4_strength,
        l4_summary, row, raw=l4_raw))

    distance_200 = abs(row.close / row.ma200 - 1)
    ma200_rising = row.ma200 >= df.ma200.iloc[-21]
    ma200_support = distance_200 <= near_pct and row.close >= row.ma200 and ma200_rising
    atr_distance_200 = abs(row.close - row.ma200) / row.atr14
    approaching_200 = not ma200_support and ma200_rising and (distance_200 <= 0.05 or atr_distance_200 <= 2.0)
    edges.append(_edge("L5", "200日线支持", "LONG", "KEY_LEVEL", ma200_support, 0.9,
        f"距离MA200={distance_200:.1%}（{atr_distance_200:.2f} ATR），MA200向上={ma200_rising}。", row,
        status="APPROACHING" if approaching_200 else None,
        raw={"distance_pct": distance_200, "atr_distance": atr_distance_200, "ma200_rising": ma200_rising}))

    swing_support = float(recent_lows.iloc[-1]) if len(recent_lows) else math.nan
    near_swing = not math.isnan(swing_support) and abs(row.close - swing_support) <= row.atr14
    edges.append(_edge("L6", "前浪底支持", "LONG", "KEY_LEVEL", near_swing and row.close >= swing_support, 0.75,
        f"最近Swing Low={swing_support:.2f}，价格距离在1 ATR以内。" if not math.isnan(swing_support) else "没有足够的Swing Low。", row))

    s1_conditions = [
        ("价格低于MA50和MA200", row.close < row.ma50 < row.ma200, 25),
        ("MA20斜率向下", row.ma20 < df.ma20.iloc[-11], 15),
        ("MA50斜率向下", row.ma50 < df.ma50.iloc[-21], 15),
        ("Lower High", lower_high, 20), ("Lower Low", lower_low, 20),
        ("60日跑输基准", row.rs60 < 0 if not math.isnan(row.rs60) else False, 5),
    ]
    s1_strength, s1_summary, s1_raw = _weighted_strength(s1_conditions)
    edges.append(_edge("S1", "一浪低于一浪", "SHORT", "TREND", s1_strength >= 0.55, s1_strength,
        s1_summary, row, raw=s1_raw))

    s2_conditions = [
        ("下跌日平均量不低于上涨日", row.down_volume20 >= row.up_volume20, 40),
        ("下跌/上涨平均量比至少1.15", row.down_volume20 >= row.up_volume20 * 1.15, 30),
        ("当日成交量高于20日均量", row.volume > row.avg_volume20, 15),
        ("价格低于MA50", row.close < row.ma50, 15),
    ]
    s2_strength, s2_summary, s2_raw = _weighted_strength(s2_conditions)
    edges.append(_edge("S2", "低量上升、大量下跌", "SHORT", "VOLUME", s2_strength >= 0.5, s2_strength,
        f"{s2_summary}；下跌/上涨平均量比={row.down_volume20 / row.up_volume20:.2f}。", row, raw=s2_raw))

    s3_conditions = [
        ("价格低于MA10", row.close < row.ma10, 10), ("价格低于MA20", row.close < row.ma20, 10),
        ("价格低于MA50", row.close < row.ma50, 15), ("MA10<MA20<MA50", row.ma10 < row.ma20 < row.ma50, 20),
        ("MA10向下", row.ma10 < df.ma10.iloc[-6], 15), ("MA20向下", row.ma20 < df.ma20.iloc[-11], 15),
        ("MA50向下", row.ma50 < df.ma50.iloc[-21], 15),
    ]
    s3_strength, s3_summary, s3_raw = _weighted_strength(s3_conditions)
    edges.append(_edge("S3", "10/20/50日线向下且高于股价", "SHORT", "MA", s3_strength >= 0.5, s3_strength,
        s3_summary, row, raw=s3_raw))

    near_ma10 = abs(row.high / row.ma10 - 1) <= 0.012
    ma10_resistance = row.close < row.ma10 and near_ma10 and row.close < row.open
    edges.append(_edge("S4", "10日线阻力", "SHORT", "KEY_LEVEL", ma10_resistance, 0.8,
        f"最高价接近MA10，收盘位于MA10下方且为阴线。", row,
        status="APPROACHING" if row.close < row.ma10 and abs(row.close / row.ma10 - 1) <= 0.025 and not ma10_resistance else None))

    broken_support = prev.close < prev.prior_low20
    resistance_retest = broken_support and row.high >= prev.prior_low20 * 0.98 and row.close < prev.prior_low20
    edges.append(_edge("S5", "支持反转成为阻力", "SHORT", "STRUCTURE", resistance_retest, 0.9,
        "20日支撑跌破后反弹测试失败。", row))

    body = abs(row.close - row.open)
    lower_shadow = min(row.open, row.close) - row.low
    high_volume = row.volume >= row.avg_volume20 * expansion
    shadow_ratio = lower_shadow / max(body, 0.01)
    long_lower_bear = row.close < row.open and shadow_ratio >= 1.0 and high_volume
    s6_strength = min(1.0, 0.35 + min(shadow_ratio / 2.0, 0.4) + (0.25 if high_volume else 0)) if row.close < row.open else 0
    edges.append(_edge("S6", "长下影阴线且成交量大", "SHORT", "TRIGGER", long_lower_bear, s6_strength,
        f"下影/实体比={lower_shadow / max(body, 0.01):.2f}，成交量比={row.volume / row.avg_volume20:.2f}；需后续跌破确认。", row,
        status="PARTIAL" if long_lower_bear else None))

    breakout = row.close > row.prior_high20 and row.volume >= row.avg_volume20 * expansion
    breakdown = row.close < row.prior_low20 and row.volume >= row.avg_volume20 * expansion
    edges.append(_edge("LT", "放量突破触发", "LONG", "TRIGGER", breakout, 1.0,
        f"收盘突破20日高点，成交量比={row.volume / row.avg_volume20:.2f}。", row))
    edges.append(_edge("ST", "放量跌破触发", "SHORT", "TRIGGER", breakdown, 1.0,
        f"收盘跌破20日低点，成交量比={row.volume / row.avg_volume20:.2f}。", row))
    return edges


def _score(edges, direction):
    category_scores = {}
    for edge in edges:
        if edge.direction == direction and edge.status in {"ACTIVE", "CONFIRMED", "PARTIAL"}:
            category_scores[edge.category] = max(category_scores.get(edge.category, 0), edge.score)
    return min(100.0, sum(category_scores.values()))


def build_scan_result(symbol, df, edges, settings):
    row = df.iloc[-1]
    long_score = _score(edges, "LONG")
    short_score = _score(edges, "SHORT")
    net = long_score - short_score
    long_trigger = any(e.code == "LT" and e.status == "ACTIVE" for e in edges)
    short_trigger = any(e.code == "ST" and e.status == "ACTIVE" for e in edges)
    threshold = settings["scan"]["candidate_score"]
    min_net = settings["scan"]["min_net_edge"]
    if long_score >= threshold and net >= min_net:
        status = "LONG_TRIGGERED" if long_trigger else "LONG_SETUP"
        stop = min(row.ma20, df.low.iloc[-10:].min()) - row.atr14 * 0.25
        entry_low, entry_high = row.close, row.close + row.atr14 * 0.5
        target = max(row.prior_high20, row.close + 3 * (row.close - stop))
        risk_reward = (target - row.close) / (row.close - stop) if row.close > stop else None
    elif short_score >= threshold and -net >= min_net:
        status = "SHORT_TRIGGERED" if short_trigger else "SHORT_SETUP"
        stop = max(row.ma20, df.high.iloc[-10:].max()) + row.atr14 * 0.25
        entry_low, entry_high = row.close - row.atr14 * 0.5, row.close
        target = min(row.prior_low20, row.close - 3 * (stop - row.close))
        risk_reward = (row.close - target) / (stop - row.close) if stop > row.close else None
    elif long_score >= 45 and short_score >= 45:
        status = "CONFLICT"
        entry_low = entry_high = stop = target = risk_reward = None
    else:
        status = "WATCHLIST"
        entry_low = entry_high = stop = target = risk_reward = None
    return ScanResult(
        symbol=symbol, scan_date=str(row.name.date()), status=status,
        long_score=round(long_score, 1), short_score=round(short_score, 1), net_score=round(net, 1),
        long_count=sum(e.direction == "LONG" and e.status in {"ACTIVE", "CONFIRMED", "PARTIAL"} for e in edges),
        short_count=sum(e.direction == "SHORT" and e.status in {"ACTIVE", "CONFIRMED", "PARTIAL"} for e in edges),
        close=round(float(row.close), 2), entry_low=_round(entry_low), entry_high=_round(entry_high),
        stop_price=_round(stop), target_price=_round(target), risk_reward=_round(risk_reward), edges=edges,
    )


def _round(value):
    return None if value is None or math.isnan(value) else round(float(value), 2)
