# TradingAgents-astock 股票分析 SKILL

用 [TradingAgents-astock](https://github.com/simonlin1212/tradingagents-astock) 多 Agent
投研框架分析指定 A 股，DeepSeek 作为 LLM，输出**机器可读的中文 JSON 报告**。

> 这是给 Agent 使用的 SKILL 的配套说明。Agent 触发时只读精简版 `SKILL.md`；
> 本文件是给人看的完整背景与参考，不进 Agent 上下文。

## 能力

- 7 个分析师角色（市场 / 情绪 / 新闻 / 基本面 / 政策 / 游资追踪 / 解禁监控）
- Bull/Bear 多空辩论（本 SKILL 固定 **3 轮**）
- 三方风险辩论（激进 / 保守 / 中性，固定 **3 轮**）
- 最终由组合经理给出五档评级：`Buy / Overweight / Hold / Underweight / Sell`
- A 股数据全部直连 HTTP（mootdx / 腾讯 / 东财 / 新浪等），**零额外 API Key**

## 固定配置

脚本 `scripts/analyze_stock.py` 内已写死以下配置，调用方无需传参：

| 项 | 值 |
|----|----|
| LLM provider | `deepseek` |
| deep 档模型（研究经理 / 组合经理） | `deepseek-v4-pro` |
| quick 档模型（7 分析师 + 辩手） | `deepseek-v4-pro` |
| API 源 | `https://api.deepseek.com`（DeepSeek 官方） |
| 输出语言 | 中文 |
| `max_debate_rounds` | 3 |
| `max_risk_discuss_rounds` | 3 |
| 数据源 | 全部 `a_stock`（直连 HTTP，零额外 key） |

## 密钥桥接机制

本 SKILL 通过 frontmatter 的 `required_environment_variables` **声明式放行**
`TRADING_AGENTS_DEEPSEEK_API_KEY`——而非靠正文文字提示用户去 export：

```yaml
required_environment_variables:
  - name: TRADING_AGENTS_DEEPSEEK_API_KEY
    prompt: "DeepSeek API 密钥（用于驱动多 Agent 分析）"
    help: "在 https://platform.deepseek.com/api_keys 创建，形如 sk-xxxx"
    required_for: "调用 DeepSeek 模型运行股票分析（无此变量脚本无法工作）"
```

Hermes 加载 skill 时会读取该字段，自动 `register_env_passthrough()` 把变量加入
session 级 sandbox 透传白名单，并在缺失时向用户索取。默认情况下 sandbox（execute_code /
terminal）会剥离密钥，声明放行后该变量才会透传给 `uv run` 拉起的脚本子进程。

脚本内部（`_inject_api_key()`）再把它桥接为项目实际读取的 `DEEPSEEK_API_KEY`——项目的
deepseek 客户端固定读后者（见 `tradingagents/llm_clients/openai_client.py` 的
`_PROVIDER_CONFIG`）。**调用方无需关心 `DEEPSEEK_API_KEY`。** 未设置时脚本以退出码 1 报错。

### 为什么用自定义变量名 `TRADING_AGENTS_DEEPSEEK_API_KEY`

Hermes 的 sandbox 有一份托管厂商凭据拦截名单（`_HERMES_PROVIDER_ENV_BLOCKLIST`），
`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`、`ANTHROPIC_API_KEY` 等都在其中，**skill 无法声明放行
它们**（安全修复 GHSA-rhgp-j443-p4rf，防止恶意 skill 把宿主凭据偷渡进沙箱子进程）。

拦截按**精确名称**匹配，`TRADING_AGENTS_DEEPSEEK_API_KEY` 是自定义名、不在名单内，因此可被
合法放行。真正的 `DEEPSEEK_API_KEY` 只在 sandbox 子进程内部由脚本改名生成，不触碰放行规则。

## 使用方法

### uv 一步到位（推荐，无需预装）

`uv run --with` 自动把依赖装进临时环境再执行：

```bash
uv run --with "tradingagents-astock @ git+https://github.com/simonlin1212/tradingagents-astock.git" \
  python scripts/analyze_stock.py 600519 2026-08-14
```

### 预装环境（反复调用更快）

先装一次，之后每次只跑第 3 步：

```bash
uv venv                                                                    # 1. 建 .venv
uv pip install "tradingagents-astock @ git+https://github.com/simonlin1212/tradingagents-astock.git"  # 2. 装依赖
uv run python scripts/analyze_stock.py 600519 2026-08-14                    # 3. 执行
```

参数：`<股票代码> <交易日 YYYY-MM-DD> [--out 路径.json]`。可选 `--out` 把 JSON 报告
另存到指定路径（stdout 仍输出同一份 JSON）。模型（`deepseek-v4-pro`）、辩论轮次（各 3 轮）、
中文输出、DeepSeek 官方源均已在脚本内固定，无需传参。

## 输出契约

- **stdout**：只有一个 JSON 对象，机器可读。
- **stderr**：进度与诊断信息（不污染 stdout，可安全用管道解析）。
- **退出码**：`0` 成功；`1` 用法/密钥错误；`2` 分析出错（stdout 仍是合法 JSON，
  带 `ok=false` 与 `error`）。

完整 JSON 结构：

```json
{
  "ok": true,
  "ticker": "600519",
  "trade_date": "2026-08-14",
  "provider": "deepseek",
  "deep_think_llm": "deepseek-v4-pro",
  "quick_think_llm": "deepseek-v4-pro",
  "max_debate_rounds": 3,
  "max_risk_discuss_rounds": 3,
  "generated_at": "2026-08-14T15:04:05",
  "signal": "Overweight",
  "reports": {
    "market_report": "……",
    "sentiment_report": "……",
    "news_report": "……",
    "fundamentals_report": "……",
    "policy_report": "……",
    "hot_money_report": "……",
    "lockup_report": "……",
    "bull_history": "……",
    "bear_history": "……",
    "research_manager": "……",
    "investment_plan": "……",
    "trader_investment_plan": "……",
    "aggressive_analyst": "……",
    "conservative_analyst": "……",
    "neutral_analyst": "……",
    "portfolio_manager": "……",
    "final_trade_decision": "……"
  }
}
```

- `signal`：五档评级之一 `Buy / Overweight / Hold / Underweight / Sell`。
- `reports`：各 Agent 分区的完整中文正文；某分区为空则该键缺省。
- 只需读结论时，取 `signal` + `reports.final_trade_decision` 即可。

只解析 stdout JSON 的推荐调用（预装环境后）：

```bash
uv run python scripts/analyze_stock.py 600519 2026-08-14 2>/dev/null | jq -r '.signal'
```

## 依赖安装补充

安装命令见上「使用方法」节（`uv run --with` 一步到位，或 `uv pip install` 预装）。以下是
补充说明：

- **本地可编辑安装**（改代码即时生效）：
  ```bash
  git clone https://github.com/simonlin1212/tradingagents-astock.git
  cd tradingagents-astock && uv pip install -e .
  ```
- DeepSeek 走核心依赖 `langchain-openai`，**无需任何可选 extra**。
- A 股数据源全部直连 HTTP，**除 DeepSeek 外不需要其它 API Key**。
- ⚠️ 不要在同一环境再装 `langchain-google-genai`（Gemini）：它要求 `httpx>=0.28`，
  与核心依赖 `mootdx` 钉死的 `httpx<0.26` 结构性冲突，会导致 `uv sync` 失败。纯 DeepSeek
  场景不受影响。
- 验证安装：`python -c "from tradingagents.graph.trading_graph import TradingAgentsGraph; print('OK')"`

## 注意事项

- `debate=3` + `risk=3` 会显著增加 LLM 调用量，单只股票分析耗时和 token 成本都高于默认
  配置（默认各 1 轮）。批量分析请预估成本。
- 交易日建议用最近的 A 股交易日；非交易日/未来日期可能导致部分数据为空。
- 历史日期分析时，数据层对无历史时点值的数据源（如实时估值）会在正文中告警，避免未来函数。
