import json
import plotly.graph_objects as go
from plotly.subplots import make_subplots


COLORS = {"LONG": "#16a34a", "SHORT": "#dc2626"}


def stock_chart(df, edge_rows, result=None, months=12, as_of=None):
    pd = __import__("pandas")
    if as_of:
        df = df.loc[df.index <= pd.Timestamp(as_of)]
    cutoff = df.index.max() - pd.DateOffset(months=months)
    view = df.loc[df.index >= cutoff]
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
        row_heights=[0.76, 0.24],
    )
    fig.add_trace(go.Candlestick(
        x=view.index, open=view.open, high=view.high, low=view.low, close=view.close,
        name="OHLC", increasing_line_color="#16a34a", decreasing_line_color="#dc2626",
    ), row=1, col=1)
    ma_colors = {10: "#64748b", 20: "#22c55e", 50: "#3b82f6", 200: "#ef4444"}
    for period, color in ma_colors.items():
        fig.add_trace(go.Scatter(
            x=view.index, y=view[f"ma{period}"], name=f"MA{period}", mode="lines",
            line={"width": 1.2, "color": color},
        ), row=1, col=1)
    volume_colors = ["#86efac" if close >= open_ else "#fca5a5" for open_, close in zip(view.open, view.close)]
    fig.add_trace(go.Bar(x=view.index, y=view.volume, name="Volume", marker_color=volume_colors), row=2, col=1)
    fig.add_trace(go.Scatter(
        x=view.index, y=view.avg_volume20, name="Avg Volume 20", mode="lines",
        line={"color": "#f59e0b", "width": 1},
    ), row=2, col=1)
    active_edges = [edge for edge in edge_rows if edge["status"] in {"ACTIVE", "CONFIRMED", "PARTIAL"}]
    for edge in active_edges:
        for marker in json.loads(edge["markers"]):
            fig.add_annotation(
                x=marker["date"], y=marker["price"], text=edge["edge_code"], showarrow=True,
                arrowhead=2, arrowcolor=COLORS[edge["direction"]], font={"color": COLORS[edge["direction"]]},
                bgcolor="rgba(255,255,255,0.85)", row=1, col=1,
            )
    if result:
        lines = [
            (result.get("stop_price"), "止损", "#dc2626"),
            (result.get("target_price"), "目标", "#16a34a"),
            (result.get("entry_low"), "入场", "#2563eb"),
        ]
        for price, label, color in lines:
            if price is not None:
                fig.add_hline(y=price, line_dash="dash", line_color=color, annotation_text=label, row=1, col=1)
    fig.update_layout(
        height=720, margin={"l": 20, "r": 20, "t": 30, "b": 20},
        xaxis_rangeslider_visible=False, hovermode="x unified", legend_orientation="h",
    )
    return fig
