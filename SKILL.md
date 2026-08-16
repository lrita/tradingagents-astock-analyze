---
name: tradingagents-astock-analyze
description: 用 TradingAgents-astock 多 Agent 投研框架 + DeepSeek 分析指定 A 股，输出机器可读的中文 JSON 报告。触发条件：用户要求分析某只 A 股（如「分析 600519」「帮我看看贵州茅台」），或需要多 Agent（市场/情绪/新闻/基本面/政策/游资/解禁 + 多空辩论 + 三方风险辩论）生成结构化投研结论。要求调用方通过环境变量 TRADING_AGENTS_DEEPSEEK_API_KEY 提供 DeepSeek 密钥。
required_environment_variables:
  - name: TRADING_AGENTS_DEEPSEEK_API_KEY
    prompt: "DeepSeek API 密钥（用于驱动多 Agent 分析）"
    help: "在 https://platform.deepseek.com/api_keys 创建，形如 sk-xxxx"
    required_for: "调用 DeepSeek 模型运行股票分析（无此变量脚本无法工作）"
---

# TradingAgents-astock 股票分析 SKILL

多 Agent 框架分析指定 A 股，DeepSeek 驱动，输出机器可读的中文 JSON 报告。
背景、完整配置与字段说明见 `README.md`。

## 密钥

`TRADING_AGENTS_DEEPSEEK_API_KEY` 已由 frontmatter 的 `required_environment_variables`
声明放行，Hermes 自动透传给脚本子进程并按需向用户索取，无需手动 export；脚本内部会桥接为
SDK 读取的 `DEEPSEEK_API_KEY`。放行机制与自定义命名原因见 `README.md`。

## 使用方法（uv 一步到位）

`uv run --with` 会自动把依赖装进临时环境再执行，无需预装（要求 Python >= 3.10）：

```bash
uv run --with "tradingagents-astock @ git+https://github.com/simonlin1212/tradingagents-astock.git" \
  python scripts/analyze_stock.py 600519 2026-08-14
```

参数：`<股票代码> <交易日 YYYY-MM-DD> [--out 路径.json]`。模型（`deepseek-v4-pro`）、
辩论轮次（各 3 轮）、中文输出、DeepSeek 官方源均已在脚本内固定，无需传参。
预装环境（反复调用更快）、可编辑安装、Gemini/httpx 冲突避坑见 `README.md`。

## 输出契约

- **stdout**：单个 JSON 对象（机器可读）。**stderr**：进度日志。
- **退出码**：`0` 成功 / `1` 用法或密钥错误 / `2` 分析出错（stdout 仍是合法 JSON，带 `ok=false`、`error`）。
- 关键字段：`signal`（五档评级 `Buy/Overweight/Hold/Underweight/Sell`）、
  `reports.final_trade_decision`（最终决策全文）；`reports` 下另有各 Agent 分区正文，全字段见 README。

```bash
# 只取评级（预装环境后，用 uv run python ...）：
uv run python scripts/analyze_stock.py 600519 2026-08-14 2>/dev/null | jq -r '.signal'
```

完整 JSON 字段、依赖安装细节、成本与未来函数等注意事项见 `README.md`。
