# 已吸收能力操作手册

本文是第 01-15 轮从 `hsliuping/TradingAgents-CN` 吸收能力后的操作员索引。除“中国市场硬风控规则”外，所有能力都默认关闭，并且只用于研究建议；它们不会生成 `Signal`、`OrderIntent`、审批或执行指令，交易闭环保持不变。

吸收原因见 `/Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md`。每轮细节见 `.handoff/round-NN-*.md`。

## TL;DR：立即试跑

```bash
.venv/bin/python scripts/absorb_dogfood.py
# 审计环境开关，然后使用 fake LLM 运行离线端到端流程，
# 并把 Markdown 报告写入 data/reports/dogfood/
```

这次运行不需要外部依赖或 API key，用来证明已吸收代码路径可离线工作。

## 吸收内容

| 阶段 | 轮次 | 提供能力 | 状态 |
|---|---|---|---|
| P1：A 股数据源 | 01-04 | AKShare / BaoStock / Tushare 适配器和 factory composite | 代码完成，默认关闭 |
| P2：资讯源与过滤器 | 05-07 | 东方财富 / 财联社 / Finnhub / Alpha Vantage client，统一 `NewsItem` 模型，去重管线 | 代码完成，默认关闭 |
| P3：中国市场硬风控 | 08 | 涨跌停 / T+1 / ST blacklist 注入 `RiskEngine` | CN 标的默认开启 |
| P4：技术特征 | 09 | `compute_technical_features(bars)` 输出 MA / MACD / RSI / BOLL / 量比 / 支撑阻力 | 始终可用，仅研究 |
| P5：股票池筛选器 | 10 | `UniverseScreener.screen(...)` 多维排序 | 始终可用，仅研究 |
| P6：LLM 研究建议层 | 11-15 | 预算门禁、provider 抽象、研究分析师、报告导出、缓存和批处理编排 | 代码完成，默认关闭 |

## 环境开关清单

`scripts/absorb_dogfood.py` 会实时打印这份清单；下表是规范参考。

### A 股行情数据（第 01-04 轮）

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `TRADINGCAT_AKSHARE_ENABLED` | `false` | 启用 AKShare 适配器（CN bars/quotes） |
| `TRADINGCAT_AKSHARE_ADJUST` | `qfq` | `""` / `qfq` / `hfq` |
| `TRADINGCAT_AKSHARE_SPOT_CACHE_TTL_SECONDS` | `30.0` | 缓存全 A 股 spot snapshot |
| `TRADINGCAT_BAOSTOCK_ENABLED` | `false` | 免费 A 股 fallback |
| `TRADINGCAT_BAOSTOCK_ADJUSTFLAG` | `2` | `1` 后复权 / `2` 前复权 / `3` 不复权 |
| `TRADINGCAT_TUSHARE_ENABLED` | `false` | Tushare Pro 适配器 |
| `TRADINGCAT_TUSHARE_TOKEN` | unset | Tushare token，仅从环境读取，禁止提交 |
| `TRADINGCAT_TUSHARE_ADJ` | `qfq` | `""` / `qfq` / `hfq` |

按需安装可选依赖：

```bash
pip install 'tradingcat[sentiment_akshare]'    # 第 01 轮
pip install 'tradingcat[sentiment_baostock]'   # 第 03 轮
pip install 'tradingcat[sentiment_tushare]'    # 第 04 轮
```

当 `TRADINGCAT_AKSHARE_ENABLED=true` 时，factory 会用 `CompositeMarketDataAdapter` 包裹现有行情链路（Futu -> YFinance -> Static），把 CN 标的路由到 AKShare，失败时回落到内部链路。BaoStock / Tushare 适配器已经按配置导入，但尚未接入 factory；它们为下一步操作员驱动接线预留。

### 资讯源（第 05-06 轮）

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `TRADINGCAT_EASTMONEY_NEWS_ENABLED` | `false` | 东方财富适配器，无需 key |
| `TRADINGCAT_EASTMONEY_NEWS_COLUMN` | `351` | 资讯栏目 id |
| `TRADINGCAT_EASTMONEY_NEWS_PAGE_SIZE` | `20` | 页面大小 |
| `TRADINGCAT_EASTMONEY_NEWS_CACHE_TTL_SECONDS` | `600` | 缓存 TTL |
| `TRADINGCAT_CLS_NEWS_ENABLED` | `false` | 财联社 web feed |
| `TRADINGCAT_CLS_NEWS_PAGE_SIZE` | `20` | 页面大小 |
| `TRADINGCAT_FINNHUB_NEWS_ENABLED` | `false` | Finnhub `company-news` |
| `TRADINGCAT_FINNHUB_TOKEN` | unset | Finnhub API token，仅环境变量 |
| `TRADINGCAT_FINNHUB_NEWS_SYMBOLS` | unset | 逗号分隔 ticker |
| `TRADINGCAT_ALPHA_VANTAGE_NEWS_ENABLED` | `false` | Alpha Vantage `NEWS_SENTIMENT` |
| `TRADINGCAT_ALPHA_VANTAGE_API_KEY` | unset | API key，仅环境变量 |
| `TRADINGCAT_ALPHA_VANTAGE_NEWS_TICKERS` | unset | 逗号分隔 ticker |

这些 client 都返回与现有 `NewsObservationService` provider shape 兼容的适配器本地 dict，但目前还没有自动接入 runtime。若要进入统一 `NewsItem` 过滤器，请在操作脚本中直接构造 client（形状参考 `scripts/absorb_dogfood.py`），再把结果传给 `tradingcat.services.news_filter`。

可选依赖，仅在东方财富 TLS fingerprint 检查变严格时需要：

```bash
pip install 'tradingcat[sentiment_eastmoney]'  # 添加 curl_cffi
```

### 统一资讯过滤器（第 07 轮）

无环境开关，是纯函数服务。入口如下：

- `tradingcat.domain.news.NewsItem`
- `tradingcat.domain.news.NewsUrgency`
- `tradingcat.domain.news.NewsEventClass`
- `tradingcat.services.news_filter`：URL 规范化、tracking 参数移除、标题去重、source allow/deny、紧急度关键词分类、freshness × source_quality × relevance × urgency 打分。

### 中国市场硬风控（第 08 轮）

| `RiskConfig` 字段 | 默认值 | 用途 |
|---|---|---|
| `cn_market_rules_enabled` | `True` | 主开关，默认开启 |
| `cn_limit_pct_regular` | `0.10` | 普通 A 股日涨跌幅限制 |
| `cn_limit_pct_st` | `0.05` | ST 股票日涨跌幅限制 |
| `cn_limit_pct_growth_board` | `0.20` | 创业板（300/301）/ 科创板（688）限制 |

这些规则不是环境变量驱动，而是配置默认值。如需不同限制，用与其他 `RiskConfig` 字段相同的机制覆盖。

规则在 `RiskEngine` 内生效，并读取：

- `Instrument.tags` 中的 `st_pattern`、`delisting_warning`。
- `metadata.limit_status` 中的 `limit_up` / `limit_down` 标注。
- `metadata.last_buy_date` / `acquired_at` / `bought_at` 中的 T+1 卖出锁定信息。

### 技术特征（第 09 轮）

```python
from tradingcat.strategies.research_candidates import compute_technical_features
snapshot = compute_technical_features(bars)
# snapshot.ma5, .ma10, .ma20, .ma60
# snapshot.macd_dif, .macd_dea, .macd_hist
# snapshot.rsi14
# snapshot.boll_upper, .boll_mid, .boll_lower
# snapshot.volume_ratio_20d
# snapshot.support, .resistance
# snapshot.trend_alignment ('bullish' / 'bearish' / 'mixed')
# snapshot.momentum_state ('overbought' / 'oversold' / 'neutral')
```

这是纯函数，无环境变量、无网络、无外部依赖。返回的 `TechnicalFeatureSnapshot` 可作为 screener / analyst 输入。

### 股票池筛选器（第 10 轮）

```python
from tradingcat.services.universe_screener import UniverseScreener
screener = UniverseScreener()  # 默认权重：0.4 technical / 0.35 fundamental / 0.25 news
candidates = screener.screen(
    instruments,
    technical={"600000": snapshot, ...},
    fundamentals={"600000": {"pe_ratio": 10.5, "roe": 0.15, ...}},
    news=[news_item, ...],
    limit=20,
)
```

返回排序后的 `UniverseCandidate`，包含各维度子分和人类可读 `reasons`。仅用于研究。

### LLM 研究建议层（第 11-15 轮）

| 环境变量 | 默认值 | 用途 |
|---|---|---|
| `TRADINGCAT_LLM_ENABLED` | `false` | 启用预算门禁 |
| `TRADINGCAT_LLM_PROVIDER` | `disabled` | `fake` / `openai_compatible`，可继续扩展 |
| `TRADINGCAT_LLM_MODEL` | unset | 模型 id，例如 `deepseek-chat`、`qwen-turbo` |
| `TRADINGCAT_LLM_DAILY_TOKEN_BUDGET` | `50000` | 每日 token 上限；超过后预算门禁拒绝 |
| `TRADINGCAT_LLM_MONTHLY_COST_BUDGET` | `25.0` | 每月美元成本上限 |

栈结构如下，每层都执行预算约束并保持 advisory-only：

```text
LLMBudgetGate            (R11) tradingcat/services/llm_budget.py
    ↓
LLMProvider              (R12) tradingcat/adapters/llm/{base,fake,openai_compatible}.py
    ↓ optionally cached
CachedLLMProvider        (R15) tradingcat/services/llm_cache.py
    ↓
ResearchAnalystService   (R13) tradingcat/services/research_analysts/
    ↓
ReportExportService      (R14) tradingcat/services/report_export.py
    ↓
BatchResearchService     (R15) tradingcat/services/batch_research.py
```

接入真实 provider（如 DeepSeek / Qwen）时，使用供应商 base URL、key 和 model id 构造 `OpenAICompatibleProvider`，再接入 `ResearchAnalystService`。预算门禁会拒绝超预算请求并抛出 `LLMProviderError`，不会进入交易路径。

## 验证已吸收路径

```bash
# 审计环境开关，并用 fake 组件跑端到端流程（无依赖、无 key、无网络）：
.venv/bin/python scripts/absorb_dogfood.py

# 只审计：
.venv/bin/python scripts/absorb_dogfood.py --skip-dogfood

# 跳过审计，只跑离线 pipeline：
.venv/bin/python scripts/absorb_dogfood.py --skip-audit

# 针对吸收能力引入测试的定向 pytest：
.venv/bin/pytest \
  tests/test_akshare_adapter.py tests/test_baostock_adapter.py tests/test_tushare_adapter.py \
  tests/test_eastmoney_news_adapter.py tests/test_news_sources_round06.py tests/test_news_filter.py \
  tests/test_research_candidate_technical_features.py \
  tests/test_universe_screener.py \
  tests/test_llm_budget.py tests/test_llm_provider.py tests/test_research_analysts.py \
  tests/test_report_export.py tests/test_llm_cache_batch_research.py \
  tests/test_adapter_factory.py tests/test_risk.py tests/test_config.py
# 预期：约 92 passed
```

## 每日研究建议报告（R15 之后接线）

这是每日一次的定时运行，触发已吸收研究 pipeline（股票池筛选器、技术特征和可选 LLM analyst），并把 Markdown artifact 写到 `data/reports/advisory/YYYY-MM-DD.md`。该流程只读，不会生成 signal、order 或 approval；磁盘文件按天滚动，并清理超过 `retention_days` 的旧文件。

默认关闭。启用方式：

```text
TRADINGCAT_ADVISORY_REPORT_ENABLED=true
# 可选覆盖项（下面是默认值）：
TRADINGCAT_ADVISORY_REPORT_CRON_HOUR=7
TRADINGCAT_ADVISORY_REPORT_CRON_MINUTE=45
TRADINGCAT_ADVISORY_REPORT_CRON_TIMEZONE=Asia/Shanghai
TRADINGCAT_ADVISORY_REPORT_OUTPUT_DIR=data/reports/advisory
TRADINGCAT_ADVISORY_REPORT_RETENTION_DAYS=30
TRADINGCAT_ADVISORY_REPORT_CANDIDATE_LIMIT=10
```

重启应用后，`GET /research/advisory/capabilities` 会显示 `daily_advisory_report` 为 `enabled: true, ready: true`，`GET /scheduler/jobs` 会列出 `advisory_research_daily` 和下一次运行时间。

各 section 的来源：

| Section | 来源 | 何时填充 |
|---|---|---|
| `## 候选标的排行` | `UniverseScreener` 基于 instrument catalogue，并使用 R09 技术特征和缓存 bars | 始终 |
| `## 资讯引用` | News provider（东方财富 / 财联社 / Finnhub / Alpha Vantage） | 一个或多个资讯适配器已配置并接线，provider hookup 是后续项 |
| `## 分析师研究` | `ResearchAnalystService` 基于 `OpenAICompatibleLLMProvider` | `LLMConfig.enabled=true`，且 `provider` / `model` / `base_url` / `api_key` 都已设置 |

未设置 LLM key 时，日报仍会生成确定性的部分；分析师块显示 `_暂无分析师输出。_`。接入真实 provider 示例：

```text
TRADINGCAT_LLM_ENABLED=true
TRADINGCAT_LLM_PROVIDER=deepseek
TRADINGCAT_LLM_MODEL=deepseek-chat
TRADINGCAT_LLM_BASE_URL=https://api.deepseek.com/v1
TRADINGCAT_LLM_API_KEY=sk-...
TRADINGCAT_LLM_COST_PER_1K_TOKENS=0.00014  # 供应商费率
```

任意时间手动运行：

```python
from tradingcat.app import TradingCatApplication
app = TradingCatApplication()
app.run_daily_advisory_research()
```

也可以用 `scripts/absorb_dogfood.py --skip-audit` 跑 synthetic 版本。

## 吸收边界

已吸收能力不会：

- 从 LLM 输出生成 `Signal` / `OrderIntent`。
- 修改 `tradingcat/strategies/simple.py` 中的生产策略；生产策略保持确定性。
- 绕过 `approval` 流程或 kill switch。
- 放宽 `RiskConfig` 规则；第 08 轮只增加 CN 特定规则，不削弱既有 US/HK 规则。
- 跳过实盘 rollout 前的纸面交易证据要求；`PLAN.md` 中 Stage A-D 仍要求 4-6 周证据。

如果发现代码越过这些边界，就是回归；应开 issue 或回退对应轮次。

## 参考入口

- 吸收计划：`/Users/miau/.claude/plans/https-github-com-hsliuping-tradingagent-peppy-pinwheel.md`
- 每轮 handoff：`.handoff/round-NN-*.md`
- 轮次索引：`.handoff/index.md`
- Dogfood 脚本：`scripts/absorb_dogfood.py`
