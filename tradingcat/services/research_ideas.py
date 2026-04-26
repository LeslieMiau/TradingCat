from __future__ import annotations

from datetime import date

from tradingcat.domain.models import Signal
from tradingcat.services.strategy_analysis import StrategyAnalysisService


class ResearchIdeasService:
    def __init__(self, strategy_analysis: StrategyAnalysisService) -> None:
        self._strategy_analysis = strategy_analysis

    def suggest_experiments(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        recommendation_report = self._strategy_analysis.recommend_strategy_actions(as_of, strategy_signals)
        experiment_ideas: list[dict[str, object]] = []

        for recommendation in recommendation_report["recommendations"]:
            strategy_id = str(recommendation["strategy_id"])
            action = str(recommendation["action"])
            metrics = recommendation["metrics"]
            max_selected_correlation = float(recommendation["max_selected_correlation"])
            turnover = float(metrics["turnover"])
            drawdown = float(metrics["max_drawdown"])

            if action == "drop":
                if max_selected_correlation >= 0.7:
                    experiment_ideas.append(
                        {
                            "strategy_id": strategy_id,
                            "priority": "high",
                            "experiment": "narrow_universe",
                            "hypothesis": "Reducing overlap may bring pairwise correlation below 0.7.",
                            "success_gate": "max_selected_correlation < 0.7",
                        }
                    )
                experiment_ideas.append(
                    {
                        "strategy_id": strategy_id,
                        "priority": "high",
                        "experiment": "tighten_filters",
                        "hypothesis": "Tighter entry filters may improve Sharpe and reduce drawdown.",
                        "success_gate": "annualized_return > 0.12 and max_drawdown < 0.12 and sharpe > 1.0",
                    }
                )
                continue

            if action == "paper_only":
                experiment_ideas.append(
                    {
                        "strategy_id": strategy_id,
                        "priority": "medium",
                        "experiment": "reduce_option_budget",
                        "hypothesis": "Lower option allocation may preserve convexity while improving capacity.",
                        "success_gate": "capacity_tier != limited or turnover declines without drawdown worsening",
                    }
                )

            if turnover > 1.5:
                experiment_ideas.append(
                    {
                        "strategy_id": strategy_id,
                        "priority": "medium",
                        "experiment": "rebalance_less_frequently",
                        "hypothesis": "Lower rebalance frequency may reduce implementation drag.",
                        "success_gate": "turnover decreases while annualized_return remains above threshold",
                    }
                )
            if drawdown >= 0.1:
                experiment_ideas.append(
                    {
                        "strategy_id": strategy_id,
                        "priority": "medium",
                        "experiment": "add_risk_filter",
                        "hypothesis": "Adding a defensive or trend filter may reduce drawdown.",
                        "success_gate": "max_drawdown improves without breaking return gate",
                    }
                )
            if action == "keep" and turnover <= 1.5 and drawdown < 0.1:
                experiment_ideas.append(
                    {
                        "strategy_id": strategy_id,
                        "priority": "low",
                        "experiment": "stability_check",
                        "hypothesis": "The current parameter set is stable enough for additional walk-forward confirmation.",
                        "success_gate": "metrics remain within current validation band over the next sample",
                    }
                )

        return {
            "as_of": as_of,
            "portfolio_passed": recommendation_report["portfolio_passed"],
            "accepted_strategy_ids": recommendation_report["accepted_strategy_ids"],
            "experiment_ideas": experiment_ideas,
            "next_actions": recommendation_report["next_actions"],
        }

    def summarize_news(self, items: list[dict[str, object]]) -> dict[str, object]:
        topics: dict[str, int] = {"macro": 0, "earnings": 0, "regulation": 0, "liquidity": 0, "technology": 0, "risk": 0}
        impacted_symbols: set[str] = set()
        highlights: list[str] = []

        for item in items:
            title = str(item.get("title", "")).strip()
            body = str(item.get("body", "")).strip()
            text = f"{title} {body}".lower()
            symbols = [str(symbol).upper() for symbol in item.get("symbols", []) if str(symbol).strip()]
            impacted_symbols.update(symbols)

            if any(keyword in text for keyword in {"fed", "inflation", "rates", "cpi", "jobs"}):
                topics["macro"] += 1
            if any(keyword in text for keyword in {"earnings", "guidance", "revenue", "profit"}):
                topics["earnings"] += 1
            if any(keyword in text for keyword in {"sec", "csrc", "regulation", "exchange", "filing"}):
                topics["regulation"] += 1
            if any(keyword in text for keyword in {"volume", "liquidity", "flow", "spread"}):
                topics["liquidity"] += 1
            if any(keyword in text for keyword in {"ai", "chip", "software", "cloud", "model"}):
                topics["technology"] += 1
            if any(keyword in text for keyword in {"risk", "downgrade", "miss", "fraud", "volatility"}):
                topics["risk"] += 1

            if title:
                highlights.append(title)

        dominant_topics = [topic for topic, count in sorted(topics.items(), key=lambda item: item[1], reverse=True) if count > 0][:3]
        summary_lines = []
        if dominant_topics:
            summary_lines.append(f"Dominant themes: {', '.join(dominant_topics)}.")
        if impacted_symbols:
            summary_lines.append(f"Watchlist impact: {', '.join(sorted(impacted_symbols))}.")
        if not summary_lines:
            summary_lines.append("从当前提供的条目中未识别出主导市场主题。")

        return {
            "item_count": len(items),
            "dominant_topics": dominant_topics,
            "impacted_symbols": sorted(impacted_symbols),
            "topic_counts": topics,
            "summary": " ".join(summary_lines),
            "highlights": highlights[:5],
            "next_actions": self._news_next_actions(dominant_topics, sorted(impacted_symbols)),
        }

    def _news_next_actions(self, dominant_topics: list[str], impacted_symbols: list[str]) -> list[str]:
        actions: list[str] = []
        if "macro" in dominant_topics:
            actions.append("Re-run ETF and broad-risk sleeves with updated macro assumptions.")
        if "earnings" in dominant_topics:
            actions.append("在下一次股票再平衡前检查财报窗口风险暴露。")
        if "regulation" in dominant_topics:
            actions.append("在启用受影响市场前先复核合规清单影响。")
        if "risk" in dominant_topics:
            actions.append("Inspect kill-switch thresholds, drawdown state, and option budget usage.")
        if impacted_symbols:
            actions.append(f"复核这些标的的仓位暴露：{', '.join(impacted_symbols[:5])}。")
        if not actions:
            actions.append("当前资讯集合暂时不需要立即采取新的研究动作。")
        return actions
