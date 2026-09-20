# JLaw Edge Scanner

一个每天运行一次的可解释股票筛选系统。它同时计算 Long Edge 与 Short Edge，在列表页比较多空优势，并在股票详情页的 K 线、成交量和均线上标出触发位置。

规则来源：`02_xWealth/02_策略学习/202609.JLaw/202609.JLaw.edge优劣势比较.md` 中的两张课程截图。

## 已实现

- 12 项参考 Edge：L1–L6、S1–S6。
- 放量突破/跌破触发条件。
- Edge 的 `APPROACHING`、`PARTIAL`、`ACTIVE`、`INACTIVE` 状态。
- Edge 子条件分项计分：局部优势不再因为一个条件失败而全部归零。
- 按趋势、量价、均线、结构、关键位置和触发分组封顶计分，降低重复信号影响。
- `LONG_SETUP`、`LONG_TRIGGERED`、`SHORT_SETUP`、`SHORT_TRIGGERED`、`CONFLICT`、`WATCHLIST` 状态。
- SQLite 每日筛选快照与 Edge 解释记录。
- 本地价格缓存。
- Streamlit 候选列表、筛选器、可点击股票详情和 Plotly K 线标记。
- 即时查询：多选现有股票或输入新代码，点击后立即分析。
- 自定义每日跟踪列表，保存在 `config/watchlist.csv`。
- 应用内使用指引及 `JLAW免费课程.md` 全文展示。
- 使用指引自动读取 Edge 参考笔记中的 Obsidian 图片嵌入，并展示 `Media/Images/` 内的课程截图。
- 每日筛选页可直接重新下载行情并刷新全部分析结果。
- 历史查询按交易日读取 SQLite 快照，历史详情图截断到所选日期。
- 离线演示模式与在线 yfinance 模式。

## 安装

建议使用 Python 3.9–3.12：

```bash
cd /Users/brucewu/Documents/00.x_os/code
python3.9 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

当前系统默认 `python3` 是 3.7，不能直接使用本项目依赖；本仓库已使用本机的 Python 3.9 在 `code/.venv` 建立并验证隔离环境。

## 首次验收：离线演示

```bash
python scripts/run_daily.py --demo
streamlit run app.py
```

演示模式会生成固定随机种子的模拟行情，不需要网络。它只用于验收页面和数据流，不用于验证策略表现。

## 每日真实扫描

编辑 `config/universe.csv` 后运行：

```bash
python scripts/run_daily.py
streamlit run app.py
```

真实模式通过 yfinance 下载行情。免费行情可能延迟、缺失或发生字段变化，正式使用前建议接入稳定的数据供应商，并在 `src/provider.py` 中实现相同接口。

## 测试

```bash
pytest -q
```

## 每天自动运行

macOS 推荐使用 `launchd`，每天北京时间 07:10 执行：

```text
/absolute/path/to/code/.venv/bin/python /absolute/path/to/code/scripts/run_daily.py
```

定时任务必须使用绝对路径，并把标准输出和错误输出保存到单独日志。首次确认真实下载、数据库写入及页面显示均正确后，再启用定时任务。

## 当前边界

- 旗形属于实验性识别，强度刻意降低。
- “支持转阻力”目前只识别最近一次 20 日支撑跌破与回测，后续应扩展成跨日状态机。
- S6 长下影放量阴线只作为潜在短仓风险；后续跌破确认尚未单独保存为跨日状态。
- 行业相对强度、财报日期、周线确认和完整历史回测尚未接入。
- 系统不连接券商，不自动下单。

## 风险说明

系统输出是规则化研究结果，不是投资建议。正式应用前必须进行包含退市股票、历史成分、手续费、滑点和跳空风险的样本外回测。
