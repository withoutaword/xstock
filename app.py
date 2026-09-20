import sys
import re
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.charts import stock_chart
from src.config import load_settings
from src.database import Database
from src.indicators import add_indicators
from src.pipeline import analyze_symbols, load_universe, run_scan
from src.provider import load_price_cache
from src.watchlist import add_to_watchlist, load_watchlist, parse_symbols, remove_from_watchlist


st.set_page_config(page_title="JLaw Edge Scanner", page_icon="📈", layout="wide")
settings = load_settings()
db_path = ROOT / "data" / "scanner.sqlite"


@st.cache_data(ttl=300)
def load_snapshot():
    if not db_path.exists():
        return None, pd.DataFrame(), None
    db = Database(db_path)
    try:
        date = db.latest_date()
        return date, pd.DataFrame(db.results(date)), db.latest_run()
    finally:
        db.close()


@st.cache_data(ttl=300)
def load_history_dates():
    if not db_path.exists():
        return []
    db = Database(db_path)
    try:
        return db.available_dates()
    finally:
        db.close()


@st.cache_data(ttl=300)
def load_results_for_date(scan_date):
    if not db_path.exists() or not scan_date:
        return pd.DataFrame()
    db = Database(db_path)
    try:
        return pd.DataFrame(db.results(scan_date))
    finally:
        db.close()


@st.cache_data(ttl=300)
def load_symbol_data(symbol):
    prices = load_price_cache(ROOT / "data" / "prices")
    if symbol not in prices:
        return pd.DataFrame()
    benchmark = prices.get(settings["universe"]["benchmark"])
    return add_indicators(prices[symbol], benchmark)


def edge_badges(edges, direction):
    active = edges[(edges.direction == direction) & edges.status.isin(["ACTIVE", "CONFIRMED", "PARTIAL"])]
    return " · ".join(f"{row.edge_code} {row['name']}" for _, row in active.iterrows()) or "—"


def overview_page(scan_date, results, latest_run):
    st.title("JLaw Edge 每日筛选")
    refresh_col, info_col = st.columns([1, 4])
    if refresh_col.button("↻ 重新查询分析", type="primary", width="stretch"):
        try:
            with st.spinner("正在下载最新行情并重新分析股票列表，请稍候……"):
                outcome = run_scan(settings, demo=False)
            load_snapshot.clear()
            load_history_dates.clear()
            load_results_for_date.clear()
            load_symbol_data.clear()
            st.session_state["refresh_message"] = outcome
            st.rerun()
        except Exception as exc:
            st.error(f"刷新失败：{exc}")
    info_col.caption("刷新会查询基础股票池与自定义跟踪列表，并覆盖同一交易日的旧快照。")
    refreshed = st.session_state.pop("refresh_message", None)
    if refreshed:
        if refreshed["errors"]:
            st.warning(
                f"刷新完成：成功 {refreshed['succeeded']}，失败 {len(refreshed['errors'])}。"
            )
            with st.expander("查看失败详情"):
                st.code("\n".join(refreshed["errors"]))
        else:
            st.success(f"刷新完成：{refreshed['scan_date']}，成功分析 {refreshed['succeeded']} 只股票。")
    if latest_run:
        state = "✅" if latest_run["status"] == "SUCCESS" else "⚠️"
        st.caption(
            f"{state} 数据日期 {scan_date} · 模式 {latest_run['mode']} · "
            f"成功 {latest_run['symbols_succeeded']}/{latest_run['symbols_total']}"
        )
    counts = results.status.value_counts()
    columns = st.columns(5)
    columns[0].metric("分析股票", len(results))
    columns[1].metric("Long", int(counts.get("LONG_SETUP", 0) + counts.get("LONG_TRIGGERED", 0)))
    columns[2].metric("Short", int(counts.get("SHORT_SETUP", 0) + counts.get("SHORT_TRIGGERED", 0)))
    columns[3].metric("冲突", int(counts.get("CONFLICT", 0)))
    columns[4].metric("新触发", int(results.status.str.contains("TRIGGERED").sum()))

    with st.sidebar:
        st.header("筛选")
        statuses = sorted(results.status.unique())
        selected_status = st.multiselect("状态", statuses, statuses)
        min_long = st.slider("最低 Long 分", 0, 100, 0)
        min_short = st.slider("最低 Short 分", 0, 100, 0)
        min_rr = st.number_input("最低结构 RR", min_value=0.0, value=0.0, step=0.5)
        search = st.text_input("股票代码")
    filtered = results[
        results.status.isin(selected_status)
        & (results.long_score >= min_long)
        & (results.short_score >= min_short)
    ].copy()
    if min_rr:
        filtered = filtered[filtered.risk_reward.fillna(0) >= min_rr]
    if search:
        filtered = filtered[filtered.symbol.str.contains(search.upper(), regex=False)]

    display = filtered.rename(columns={
        "symbol": "股票", "status": "状态", "long_score": "Long分", "short_score": "Short分",
        "net_score": "净优势", "long_count": "Long数", "short_count": "Short数",
        "close": "收盘", "risk_reward": "RR", "entry_low": "入场下限", "entry_high": "入场上限",
        "stop_price": "止损", "target_price": "目标",
    })
    visible = ["股票", "状态", "Long分", "Short分", "净优势", "Long数", "Short数", "RR", "收盘"]
    st.subheader("候选股票")
    event = st.dataframe(
        display[visible], width="stretch", hide_index=True,
        on_select="rerun", selection_mode="single-row",
        column_config={"Long分": st.column_config.ProgressColumn(min_value=0, max_value=100),
                       "Short分": st.column_config.ProgressColumn(min_value=0, max_value=100)},
    )
    if event.selection.rows:
        symbol = display.iloc[event.selection.rows[0]]["股票"]
        st.session_state["selected_symbol"] = symbol
        st.session_state["selected_date"] = scan_date
        st.rerun()
    st.caption("点击任意一行进入股票详情。灰色 Watchlist 表示有局部优势，但尚未达到候选阈值。")


def detail_page(symbol, scan_date, results):
    row = results.loc[results.symbol == symbol].iloc[0].to_dict()
    db = Database(db_path)
    try:
        edges = pd.DataFrame(db.edges(symbol, scan_date))
    finally:
        db.close()
    prices = load_symbol_data(symbol)
    top = st.columns([1, 5])
    if top[0].button("← 返回列表"):
        st.session_state.pop("selected_symbol", None)
        st.session_state.pop("selected_date", None)
        st.rerun()
    top[1].title(f"{symbol} · {row['status']}")
    metrics = st.columns(5)
    metrics[0].metric("Long", f"{row['long_score']:.0f}")
    metrics[1].metric("Short", f"{row['short_score']:.0f}")
    metrics[2].metric("净优势", f"{row['net_score']:+.0f}")
    metrics[3].metric("结构 RR", "—" if pd.isna(row["risk_reward"]) else f"{row['risk_reward']:.2f}R")
    metrics[4].metric("收盘", f"{row['close']:.2f}")

    long_edges = edge_badges(edges, "LONG")
    short_edges = edge_badges(edges, "SHORT")
    st.success(f"Long Edge：{long_edges}")
    st.error(f"Short Edge / 风险：{short_edges}")
    months = st.segmented_control("范围", [3, 6, 12, 24], default=12)
    if prices.empty:
        st.warning("没有找到价格缓存，请重新运行每日扫描。")
    else:
        st.plotly_chart(
            stock_chart(prices, edges.to_dict("records"), row, months, as_of=scan_date),
            width="stretch",
        )

    left, right = st.columns(2)
    for container, direction, title in ((left, "LONG", "Long Edge"), (right, "SHORT", "Short Edge / 劣势")):
        container.subheader(title)
        direction_edges = edges[edges.direction == direction]
        for _, edge in direction_edges.iterrows():
            icon = "✅" if edge.status in {"ACTIVE", "CONFIRMED"} else "◐" if edge.status == "PARTIAL" else "⏳" if edge.status == "APPROACHING" else "○"
            with container.expander(f"{icon} {edge.edge_code} · {edge['name']} · {edge.status}"):
                st.write(edge.explanation)
                st.caption(f"类别 {edge.category} · 强度 {edge.strength:.0%} · 得分 {edge.score:.1f}")

    st.subheader("交易结构（仅供研究）")
    plan = pd.DataFrame([{
        "入场下限": row["entry_low"], "入场上限": row["entry_high"], "失效/止损": row["stop_price"],
        "结构目标": row["target_price"], "结构RR": row["risk_reward"],
    }])
    st.dataframe(plan, hide_index=True, width="stretch")
    st.warning("系统输出是规则化研究结果，不是投资建议；目标位和止损位需要结合实际滑点、跳空与流动性。")


def query_page():
    st.title("即时查询与跟踪")
    st.write("从股票池选择，或输入新的美股代码；点击后立即下载最近两年行情并计算 Long/Short Edge。")
    universe = load_universe(settings)
    existing = sorted(universe.symbol.dropna().str.upper().unique())
    selected = st.multiselect("从现有股票池选择", existing, placeholder="选择一只或多只股票")
    typed = st.text_area(
        "输入其他股票代码",
        placeholder="例如：MU, SNDK, DELL, INTC\n可使用逗号、空格或换行分隔",
        height=90,
    )
    track = st.checkbox("将输入的新股票加入每日跟踪列表", value=True)
    run = st.button("查询分析", type="primary", width="stretch")
    if run:
        try:
            manual = parse_symbols(typed)
            symbols = list(dict.fromkeys(selected + manual))
            if not symbols:
                st.warning("请至少选择或输入一个股票代码。")
            else:
                with st.spinner(f"正在下载并分析 {len(symbols)} 只股票……"):
                    analyzed, errors = analyze_symbols(settings, symbols, demo=False, persist=True)
                    if track and manual:
                        add_to_watchlist(ROOT / "config" / "watchlist.csv", manual)
                load_snapshot.clear()
                load_symbol_data.clear()
                st.session_state["query_symbols"] = [item.symbol for item in analyzed]
                st.session_state["query_errors"] = errors
                st.rerun()
        except Exception as exc:
            st.error(f"查询失败：{exc}")

    queried = st.session_state.get("query_symbols", [])
    errors = st.session_state.get("query_errors", [])
    if errors:
        for error in errors:
            st.error(error)
    if queried:
        date, all_results, _ = load_snapshot()
        subset = all_results[all_results.symbol.isin(queried)].copy()
        if not subset.empty:
            st.subheader(f"查询结果 · {date}")
            subset["优势摘要"] = subset.apply(
                lambda row: f"Long {int(row.long_count)} / Short {int(row.short_count)}", axis=1
            )
            shown = subset[["symbol", "status", "long_score", "short_score", "net_score", "优势摘要"]].rename(
                columns={"symbol": "股票", "status": "状态", "long_score": "Long分",
                         "short_score": "Short分", "net_score": "净优势"}
            )
            event = st.dataframe(
                shown, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row"
            )
            if event.selection.rows:
                st.session_state["selected_symbol"] = shown.iloc[event.selection.rows[0]]["股票"]
                st.session_state["selected_date"] = date
                st.rerun()
            st.caption("点击结果行进入走势图与优势/劣势详情。")

    st.divider()
    st.subheader("每日跟踪列表")
    watchlist_path = ROOT / "config" / "watchlist.csv"
    tracked = load_watchlist(watchlist_path)
    if tracked.empty:
        st.caption("尚未添加自定义跟踪股票。基础股票池仍会正常执行每日扫描。")
    else:
        st.dataframe(tracked, hide_index=True, width="stretch")
        remove = st.multiselect("从自定义跟踪列表移除", tracked.symbol.tolist())
        if st.button("移除所选", disabled=not remove):
            remove_from_watchlist(watchlist_path, remove)
            st.success("已更新跟踪列表。")
            st.rerun()


def guide_page():
    st.title("使用指引与 JLaw 免费课程")
    st.subheader("系统使用方法")
    st.markdown(
        """
1. **每日筛选**：查看定时任务生成的全部股票结果；点击任意行进入详情。
2. **即时查询**：选择或输入股票代码，点击“查询分析”。新代码可保存到每日跟踪列表。
3. **重新查询分析**：在每日筛选页点击刷新按钮，立即更新整个股票列表。
4. **历史查询**：选择过去的交易日，查看当日保存的评分、Edge 和截止当日的走势图。
5. **Long/Short 分数**：同一类别只取最高分，降低相关指标重复计分的问题。
6. **Edge 状态**：`ACTIVE` 表示主要条件成立，`PARTIAL` 表示部分成立，`APPROACHING` 表示接近关键位置。
7. **走势图标记**：L1–L6 为长仓优势，S1–S6 为短仓优势或长仓劣势；点击下方卡片查看满足和未满足的子条件。
8. **每日更新**：可点击页面刷新，也可运行 `python scripts/run_daily.py`。

> 系统结果用于研究，不是投资建议。`WATCHLIST` 也可能有多个 Edge，只是尚未满足候选分数、净优势或交易触发要求。
"""
    )
    st.divider()
    st.subheader("课程截图：Long Edge 与 Short Edge 对比")
    reference_path = (
        ROOT.parent
        / "02_xWealth"
        / "02_策略学习"
        / "202609.JLaw"
        / "202609.JLaw.edge优劣势比较.md"
    )
    if reference_path.exists():
        reference_text = reference_path.read_text(encoding="utf-8")
        image_names = re.findall(r"!\[\[([^\]|]+\.(?:png|jpg|jpeg|webp))(?:\|[^\]]+)?\]\]", reference_text, re.IGNORECASE)
        captions = {
            "截屏2026-09-20 14.29.23.png": "Long Edge 示例：强劲上升趋势、上涨放量/回调缩量、旗形整理、均线多头排列与 MA200 支撑，同时保留放量长下影阴线这一 Short Edge。",
            "截屏2026-09-20 14.32.44.png": "Short Edge 示例：Lower High/Low、上涨缩量/下跌放量、均线空头排列、MA10 阻力及支撑转阻力，同时保留 MA200 与前浪底支持。",
        }
        image_root = ROOT.parent / "Media" / "Images"
        if image_names:
            for image_name in image_names:
                image_path = image_root / image_name
                if image_path.exists():
                    st.image(
                        str(image_path),
                        caption=captions.get(image_name, image_name),
                        width="stretch",
                    )
                else:
                    st.warning(f"参考笔记中的图片不存在：{image_path}")
        else:
            st.info("参考笔记中没有找到 Obsidian 图片嵌入。")
    else:
        st.warning(f"没有找到 Edge 参考笔记：{reference_path}")

    st.divider()
    note_path = ROOT.parent / "JLAW免费课程.md"
    st.subheader("JLaw 免费课程笔记")
    if note_path.exists():
        st.markdown(note_path.read_text(encoding="utf-8"))
    else:
        st.warning(f"没有找到课程笔记：{note_path}")


def history_page():
    st.title("历史查询")
    dates = load_history_dates()
    if not dates:
        st.info("尚无历史快照。运行每日扫描后，这里会按交易日保存记录。")
        return
    selected_date = st.selectbox("选择交易日", dates, index=0)
    history = load_results_for_date(selected_date)
    if history.empty:
        st.warning("该日期没有筛选结果。")
        return
    counts = history.status.value_counts()
    metrics = st.columns(5)
    metrics[0].metric("记录数", len(history))
    metrics[1].metric("Long", int(counts.get("LONG_SETUP", 0) + counts.get("LONG_TRIGGERED", 0)))
    metrics[2].metric("Short", int(counts.get("SHORT_SETUP", 0) + counts.get("SHORT_TRIGGERED", 0)))
    metrics[3].metric("冲突", int(counts.get("CONFLICT", 0)))
    metrics[4].metric("Watchlist", int(counts.get("WATCHLIST", 0)))
    statuses = sorted(history.status.unique())
    selected_status = st.multiselect("状态", statuses, statuses, key="history_status")
    filtered = history[history.status.isin(selected_status)].copy()
    shown = filtered[[
        "symbol", "status", "long_score", "short_score", "net_score",
        "long_count", "short_count", "risk_reward", "close",
    ]].rename(columns={
        "symbol": "股票", "status": "状态", "long_score": "Long分", "short_score": "Short分",
        "net_score": "净优势", "long_count": "Long数", "short_count": "Short数",
        "risk_reward": "RR", "close": "收盘",
    })
    event = st.dataframe(
        shown, hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row"
    )
    if event.selection.rows:
        st.session_state["selected_symbol"] = shown.iloc[event.selection.rows[0]]["股票"]
        st.session_state["selected_date"] = selected_date
        st.rerun()
    st.caption("点击任意记录查看该交易日的 Edge 详情；走势图只显示截至当日的数据。")


scan_date, results, latest_run = load_snapshot()
selected_symbol = st.session_state.get("selected_symbol")
selected_date = st.session_state.get("selected_date", scan_date)
selected_results = load_results_for_date(selected_date) if selected_date else results
if selected_symbol and not selected_results.empty and selected_symbol in set(selected_results.symbol):
    detail_page(selected_symbol, selected_date, selected_results)
else:
    page = st.sidebar.radio("页面", ["每日筛选", "即时查询", "历史查询", "使用指引"])
    if page == "即时查询":
        query_page()
    elif page == "使用指引":
        guide_page()
    elif page == "历史查询":
        history_page()
    elif results.empty:
        st.title("JLaw Edge Scanner")
        st.info("尚无扫描结果。先运行：`python scripts/run_daily.py --demo`，再刷新页面。")
    else:
        overview_page(scan_date, results, latest_run)
