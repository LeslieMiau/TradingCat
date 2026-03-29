from pathlib import Path
import re


_ROUTE_DIR = Path(__file__).resolve().parents[1] / "tradingcat" / "routes"
_APP_FILE = Path(__file__).resolve().parents[1] / "tradingcat" / "app.py"
_FACADE_FILE = Path(__file__).resolve().parents[1] / "tradingcat" / "facades.py"
_SIMPLE_STRATEGIES_FILE = Path(__file__).resolve().parents[1] / "tradingcat" / "strategies" / "simple.py"
_PRIVATE_ATTR_PATTERN = re.compile(r"\.\_[A-Za-z]\w*")
_BANNED_ROUTE_TOKENS = (
    "strategy_analysis.",
    "research_ideas.",
    "trading_journal.latest_plan",
    "trading_journal.latest_summary",
    "rollout_policy.apply_recommendation",
    "alerts.evaluate(",
    "audit.execution_metrics_summary()",
    "execution.transaction_cost_summary()",
    "apply_fill_to_portfolio(",
)
_BANNED_APP_FACADE_TOKENS = (
    "strategy_analysis.",
)
_RESEARCH_CANDIDATE_CLASS_MARKERS = (
    "class MeanReversionStrategy(",
    "class DefensiveTrendStrategy(",
    "class AllWeatherStrategy(",
    "class Jianfang3LStrategy(",
)


def test_routes_do_not_access_private_members():
    violations: list[str] = []
    for path in sorted(_ROUTE_DIR.glob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _PRIVATE_ATTR_PATTERN.search(line):
                violations.append(f"{path.name}:{line_number}: {line.strip()}")
    assert violations == []


def test_routes_do_not_inline_complex_orchestration_calls():
    violations: list[str] = []
    for path in sorted(_ROUTE_DIR.glob("*.py")):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for token in _BANNED_ROUTE_TOKENS:
                if token in line:
                    violations.append(f"{path.name}:{line_number}: {line.strip()}")
    assert violations == []


def test_app_and_facades_do_not_reach_back_into_strategy_analysis_orchestration():
    violations: list[str] = []
    for path in (_APP_FILE, _FACADE_FILE):
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for token in _BANNED_APP_FACADE_TOKENS:
                if token in line:
                    violations.append(f"{path.name}:{line_number}: {line.strip()}")
    assert violations == []


def test_simple_strategy_module_keeps_research_candidates_in_dedicated_module():
    source = _SIMPLE_STRATEGIES_FILE.read_text(encoding="utf-8")
    violations = [marker for marker in _RESEARCH_CANDIDATE_CLASS_MARKERS if marker in source]
    assert violations == []
