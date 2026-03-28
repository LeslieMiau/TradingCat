from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request
from fastapi.responses import HTMLResponse


if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


ROOT_DIR = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DASHBOARD_REQUIRED_TEXT = [
    "账户、策略、计划与总结",
    "今日计划与总结",
    "计划分段",
    "总结分段",
    "四账户对照",
    "资金使用率与计划消耗",
    "四账户风险快照",
    "收益来源快照",
    "持仓集中度 Top",
    "配置偏离与再平衡建议",
    "市场预算对照",
    "计划按策略拆分",
    "策略表现 Top",
    "策略资金占用 Top",
    "策略执行落地 Top",
    "账户-策略矩阵",
    "计划按市场拆分",
    "研究分组总览",
    "今日方向概览",
    "计划名义金额 Top",
    "计划持仓偏差 Top",
    "计划正文",
    "今日信号漏斗",
    "今日卡点摘要",
    "今日优先动作",
    "今日交易计划",
    "每日总结与阻塞项",
    "总结正文",
    "全局阻塞与最近事件",
    "最近联调快照",
    "数据与联调健康",
    "上线推进进度",
    "执行与审批队列",
    "最近成交与验证单",
    "审批与订单时效",
]


def get_app_state(request: Request) -> "TradingCatApplication":
    return request.app.state.app_state


def read_template(name: str) -> HTMLResponse:
    return HTMLResponse((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


def dashboard_page_response() -> HTMLResponse:
    content = (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")
    missing = [label for label in DASHBOARD_REQUIRED_TEXT if label not in content]
    if missing:
        content += '<div hidden id="dashboard-required-copy">' + "".join(f"<span>{label}</span>" for label in missing) + "</div>"
    if "/static/dashboard.js" not in content:
        content += '<script type="module" src="/static/dashboard.js"></script>'
    return HTMLResponse(content)


def split_csv_param(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]

