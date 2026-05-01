from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _route_paths() -> set[str]:
    paths: set[str] = set()
    for path in (ROOT / "tradingcat" / "routes").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        prefix_match = re.search(r"router\s*=\s*APIRouter\(prefix=[\"']([^\"']*)[\"']", text)
        prefix = prefix_match.group(1) if prefix_match else ""
        for _method, raw_path in re.findall(r"@router\.(get|post|put|delete|patch)\([\"']([^\"']*)[\"']", text):
            route_path = f"{prefix}{raw_path}" or "/"
            paths.add(re.sub(r"\{[^}]+\}", "{}", route_path))
    return paths


def _static_api_paths() -> set[str]:
    text = (ROOT / "static" / "api.js").read_text(encoding="utf-8")
    raw_paths = []
    raw_paths.extend(re.findall(r"\"(/[^\"?]+)(?:\?[^\"\n]*)?\"", text))
    raw_paths.extend(re.findall(r"`(/[^`?]+)(?:\?[^`\n]*)?`", text))
    return {re.sub(r"\$\{[^}]+\}", "{}", raw_path) for raw_path in raw_paths}


def _scheduler_job_ids() -> set[str]:
    text = (ROOT / "tradingcat" / "scheduler_runtime.py").read_text(encoding="utf-8")
    return set(re.findall(r"job_id=[\"']([^\"']+)[\"']", text))


def _frontend_scheduler_job_ids() -> set[str]:
    job_ids: set[str] = set()
    for path in (ROOT / "static").glob("*.js"):
        text = path.read_text(encoding="utf-8")
        job_ids.update(re.findall(r"API\.schedulerRun\([\"']([^\"']+)[\"']\)", text))
        for block in re.findall(r"const CYCLE_BUTTONS = \[(.*?)\];", text, flags=re.S):
            job_ids.update(re.findall(r"\[[\"'][^\"']+[\"'],\s*[\"']([^\"']+)[\"'],", block))
        for block in re.findall(r"const ordered = \[(.*?)\];", text, flags=re.S):
            job_ids.update(re.findall(r"[\"']([^\"']+)[\"']", block))
    return job_ids


def test_static_api_paths_have_backend_routes():
    assert sorted(_static_api_paths() - _route_paths()) == []


def test_frontend_scheduler_job_ids_exist_in_registry():
    assert sorted(_frontend_scheduler_job_ids() - _scheduler_job_ids()) == []


def test_today_cockpit_frontend_is_get_only_and_no_execution_mutations():
    text = (ROOT / "static" / "dashboard_today.js").read_text(encoding="utf-8")
    forbidden = [
        "method: 'POST'",
        'method: "POST"',
        "method: 'PUT'",
        'method: "PUT"',
        "method: 'DELETE'",
        'method: "DELETE"',
        "approvalApprove",
        "ordersCancelOpen",
        "executionRun",
        "reconcile",
    ]

    assert [token for token in forbidden if token in text] == []
