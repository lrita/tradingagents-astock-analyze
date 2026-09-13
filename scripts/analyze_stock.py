#!/usr/bin/env python3
"""通过 TradingAgents-astock SDK 分析指定 A 股，输出机器可读的 JSON 报告。

用法：
    python analyze_stock.py <股票代码> <交易日 YYYY-MM-DD> [--out 路径.json]

例：
    python analyze_stock.py 600519 2026-08-14
    python analyze_stock.py 600519 2026-08-14 --out /tmp/report.json

约定（供 Agent 调用）：
  · 密钥：从环境变量 TRADING_AGENTS_DEEPSEEK_API_KEY 读取，脚本内部会把它
    注入为项目实际读取的 DEEPSEEK_API_KEY。二者都没有则报错退出。
  · stdout：只打印一个 JSON 对象（机器可读）。所有进度/诊断走 stderr，
    互不污染，可安全用管道解析。
  · 退出码：0 成功，1 用法/密钥错误，2 分析过程出错（stdout 仍是合法 JSON，
    带 ok=false 与 error 字段）。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime


def _eprint(msg: str) -> None:
    """诊断信息一律走 stderr，保证 stdout 是纯净 JSON。"""
    print(msg, file=sys.stderr, flush=True)


def _inject_api_key() -> None:
    """把 TRADING_AGENTS_DEEPSEEK_API_KEY 映射注入到项目读取的 DEEPSEEK_API_KEY。

    项目的 deepseek 客户端固定用 os.environ["DEEPSEEK_API_KEY"] 取密钥
    （见 tradingagents/llm_clients/openai_client.py 的 _PROVIDER_CONFIG）。
    Agent 只需传 TRADING_AGENTS_DEEPSEEK_API_KEY，这里做一次桥接。
    """
    key = os.environ.get("TRADING_AGENTS_DEEPSEEK_API_KEY")
    if not key:
        _eprint(
            "错误：未设置环境变量 TRADING_AGENTS_DEEPSEEK_API_KEY。\n"
            "请先 export TRADING_AGENTS_DEEPSEEK_API_KEY=你的deepseek密钥 再运行。"
        )
        sys.exit(1)
    # 注入到子进程（即本进程）环境，供 SDK 构造 LLM 时读取。
    os.environ["DEEPSEEK_API_KEY"] = key


def _build_config() -> dict:
    """构造 DeepSeek + A 股数据源的运行配置。"""
    from tradingagents.default_config import DEFAULT_CONFIG

    config = DEFAULT_CONFIG.copy()
    # ── LLM：DeepSeek 官方源 ──────────────────────────────────────────────
    config["llm_provider"] = "deepseek"
    config["deep_think_llm"] = "deepseek-flash"   # 深度节点：研究经理 / 组合经理
    config["quick_think_llm"] = "deepseek-flash"  # 快速节点：7 分析师 + 多空/风险辩手
    config["backend_url"] = "https://api.deepseek.com"  # deepseek 官方 API 源
    # ── A 股数据源（全部直连 HTTP，零额外 API Key）──────────────────────
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    # ── 输出 & 辩论轮次 ──────────────────────────────────────────────────
    config["output_language"] = "Chinese"
    config["max_debate_rounds"] = 3        # 多空辩论 3 轮
    config["max_risk_discuss_rounds"] = 3  # 风险辩论 3 轮
    return config


def _collect_reports(final_state: dict) -> dict:
    """从最终状态里抽出各分区报告，组装成结构化字典。"""
    reports: dict = {}

    # 7 个分析师 + 交易/决策的顶层报告
    top_keys = [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "policy_report",
        "hot_money_report",
        "lockup_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ]
    for key in top_keys:
        val = final_state.get(key)
        if val:
            reports[key] = val

    # 多空辩论
    debate = final_state.get("investment_debate_state", {}) or {}
    if debate:
        reports["bull_history"] = debate.get("bull_history", "")
        reports["bear_history"] = debate.get("bear_history", "")
        reports["research_manager"] = debate.get("judge_decision", "")

    # 三方风险辩论
    risk = final_state.get("risk_debate_state", {}) or {}
    if risk:
        reports["aggressive_analyst"] = risk.get("aggressive_history", "")
        reports["conservative_analyst"] = risk.get("conservative_history", "")
        reports["neutral_analyst"] = risk.get("neutral_history", "")
        reports["portfolio_manager"] = risk.get("judge_decision", "")

    return reports


def main() -> None:
    parser = argparse.ArgumentParser(
        description="用 TradingAgents-astock + DeepSeek 分析 A 股，输出 JSON 报告。"
    )
    parser.add_argument("ticker", help="6 位 A 股代码，如 600519")
    parser.add_argument("trade_date", help="交易日，格式 YYYY-MM-DD")
    parser.add_argument(
        "--out",
        default=None,
        help="可选：把 JSON 报告另存到此路径（stdout 仍会输出同一份 JSON）。",
    )
    args = parser.parse_args()

    # 1) 密钥桥接：TRADING_AGENTS_DEEPSEEK_API_KEY → DEEPSEEK_API_KEY
    _inject_api_key()

    # 2) 延迟 import：确保在密钥注入之后，且 import 失败能给出清晰提示
    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph
    except ImportError as e:
        _eprint(
            f"错误：无法导入 tradingagents，依赖可能未安装：{e}\n"
            "请先安装依赖（见 SKILL.md「依赖安装」一节）。"
        )
        sys.exit(1)

    config = _build_config()

    _eprint(f"[{datetime.now():%H:%M:%S}] 开始分析 {args.ticker} @ {args.trade_date}")
    _eprint("  provider=deepseek  model=deepseek-flash  debate=3  risk=3")

    # 3) 运行分析。debug=False → 不产生流式日志，stdout 保持纯净。
    result: dict = {
        "ok": False,
        "ticker": args.ticker,
        "trade_date": args.trade_date,
        "provider": "deepseek",
        "deep_think_llm": config["deep_think_llm"],
        "quick_think_llm": config["quick_think_llm"],
        "max_debate_rounds": config["max_debate_rounds"],
        "max_risk_discuss_rounds": config["max_risk_discuss_rounds"],
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    exit_code = 0
    try:
        ta = TradingAgentsGraph(debug=False, config=config)
        final_state, decision = ta.propagate(args.ticker, args.trade_date)
        result["ok"] = True
        result["signal"] = decision  # 五档评级：Buy/Overweight/Hold/Underweight/Sell
        result["reports"] = _collect_reports(final_state)
        _eprint(f"[{datetime.now():%H:%M:%S}] 完成，评级：{decision}")
    except Exception as e:  # noqa: BLE001 — 顶层兜底，保证 stdout 仍是合法 JSON
        result["ok"] = False
        result["error"] = f"{type(e).__name__}: {e}"
        exit_code = 2
        _eprint(f"[{datetime.now():%H:%M:%S}] 分析失败：{result['error']}")

    payload = json.dumps(result, ensure_ascii=False, indent=2)

    # 4) 可选落盘
    if args.out:
        try:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(payload)
            _eprint(f"报告已另存到 {args.out}")
        except OSError as e:
            _eprint(f"警告：写入 --out 失败：{e}")

    # 5) stdout 只输出这一份 JSON
    print(payload)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
