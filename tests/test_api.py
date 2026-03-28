from fastapi.testclient import TestClient

from tradingcat.main import app, app_state

client = TestClient(app)


def test_research_backtest_endpoints():
    experiments = client.get("/research/backtests")
    assert experiments.status_code == 200
    assert len(experiments.json()) >= 0

    if len(experiments.json()) >= 2:
        left_id = experiments.json()[0]["experiment_id"]
        right_id = experiments.json()[1]["experiment_id"]
        response = client.get("/research/backtests/compare", params={"left_id": left_id, "right_id": right_id})
        assert response.status_code == 200
        compared = response.json()
        assert "same_inputs" in compared
        assert "input_diff" in compared
        assert "metric_diff" in compared


def test_research_interfaces_expose_data_blockers():
    report = client.post("/research/report/run")
    assert report.status_code == 200
    report_payload = report.json()
    assert "blocked_count" in report_payload
    assert "blocked_strategy_ids" in report_payload
    assert "strategy_reports" in report_payload
    assert "promotion_blocked" in report_payload["strategy_reports"][0]
    assert "blocking_reasons" in report_payload["strategy_reports"][0]

    scorecard = client.post("/research/scorecard/run")
    assert scorecard.status_code == 200
    scorecard_payload = scorecard.json()
    assert "blocked_count" in scorecard_payload
    assert "blocked_strategy_ids" in scorecard_payload
    assert "promotion_blocked" in scorecard_payload["rows"][0]
    assert "blocking_reasons" in scorecard_payload["rows"][0]

    strategy_id = scorecard_payload["rows"][0]["strategy_id"]
    detail = client.get(f"/research/strategies/{strategy_id}")
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert "data_source" in detail_payload
    assert "data_ready" in detail_payload
    assert "promotion_blocked" in detail_payload
    assert "blocking_reasons" in detail_payload


def test_scheduler_and_market_session_endpoints():
    sessions = client.get("/market-sessions")
    assert sessions.status_code == 200
    assert set(sessions.json().keys()) == {"US", "HK", "CN"}

    jobs = client.get("/scheduler/jobs")
    assert jobs.status_code == 200
    assert len(jobs.json()) == 11
    assert any(job["id"] == "approval_expiry_sweep" for job in jobs.json())
    assert any(job["id"] == "operations_readiness_journal" for job in jobs.json())
    assert any(job["id"] == "broker_auto_recovery" for job in jobs.json())
    assert any(job["id"] == "market_data_history_sync" for job in jobs.json())
    assert any(job["id"] == "market_data_gap_repair" for job in jobs.json())
    assert any(job["id"] == "research_selection_review" for job in jobs.json())

    run = client.post("/scheduler/jobs/portfolio_risk_snapshot/run")
    assert run.status_code == 200
    assert run.json()["status"] == "success"


def test_scheduler_selection_review_job_refreshes_allocations():
    run = client.post("/scheduler/jobs/research_selection_review/run")
    assert run.status_code == 200
    payload = run.json()
    assert payload["status"] == "success"
    allocation_summary = client.get("/research/allocations/summary")
    assert allocation_summary.status_code == 200
    assert allocation_summary.json()["count"] == 7


def test_app_lifespan_starts_scheduler():
    with TestClient(app) as lifespan_client:
        response = lifespan_client.get("/scheduler/jobs")

    assert response.status_code == 200
    assert app_state.scheduler.is_running is False


def test_portfolio_risk_state_endpoint():
    response = client.post(
        "/portfolio/risk-state",
        json={"drawdown": 0.03, "daily_pnl": -1000.0, "weekly_pnl": -2000.0},
    )
    assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_preflight_and_broker_recovery_endpoints():
    preflight = client.get("/preflight/startup")
    assert preflight.status_code == 200
    preflight_payload = preflight.json()
    assert preflight_payload["healthy"] is True
    assert "checks" in preflight_payload
    assert "recommendations" in preflight_payload

    broker_status = client.get("/broker/status")
    assert broker_status.status_code == 200
    status_payload = broker_status.json()
    assert "healthy" in status_payload
    assert "backend" in status_payload
    assert "detail" in status_payload

    broker_recover = client.post("/broker/recover")
    assert broker_recover.status_code == 200
    recovery_payload = broker_recover.json()
    assert recovery_payload["attempted"] is True
    assert "before" in recovery_payload
    assert "after" in recovery_payload
    assert "broker_status" in recovery_payload["before"]
    assert "broker_status" in recovery_payload["after"]
    assert "live_broker_adapter" in recovery_payload["after"]

    diagnostics = client.get("/diagnostics/summary")
    assert diagnostics.status_code == 200
    diagnostics_payload = diagnostics.json()
    assert "ready" in diagnostics_payload
    assert "diagnostics" in diagnostics_payload
    assert "broker_status" in diagnostics_payload

    readiness = client.get("/ops/readiness")
    assert readiness.status_code == 200
    readiness_payload = readiness.json()
    assert "ready" in readiness_payload
    assert "diagnostics" in readiness_payload
    assert "broker_status" in readiness_payload

    dashboard = client.get("/dashboard/summary")
    assert dashboard.status_code == 200
    dashboard_payload = dashboard.json()
    assert "details" in dashboard_payload
    assert "live_acceptance" in dashboard_payload["details"]


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "{% extends" not in page.text
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "账户总览" in page.text
    assert "Alpha Radar" in page.text
    assert "Macro Calendar" in page.text
    assert "计划正文" in page.text
    assert "今日计划摘要" in page.text
    assert "待审批与节奏" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "今日总结" in page.text
    assert "本周总结" in page.text
    assert "阻塞与待处理" in page.text
    assert "执行与审批队列" in page.text
    assert "待审批" in page.text
    assert "最近订单" in page.text
    assert "最近成交" in page.text
    assert "最近验证单" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/api.js" in page.text
    assert "/static/components.js" in page.text
    assert "/static/dashboard_accounts.js" in page.text
    assert "/static/dashboard_strategy.js" in page.text
    assert "/static/dashboard_operations.js" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "dashboardAccounts?.renderOverview" in js.text
    assert "dashboardStrategy?.renderPlan" in js.text
    assert "dashboardOperations?.renderSummaries" in js.text
    assert "API.dashboardSummary" in js.text
    assert "API.portfolioRebalancePlan" in js.text

    accounts_js = client.get("/static/dashboard_accounts.js")
    assert accounts_js.status_code == 200
    assert "DashboardAccounts" in accounts_js.text
    assert "function renderOverview" in accounts_js.text
    assert "function renderAssets" in accounts_js.text

    strategy_js = client.get("/static/dashboard_strategy.js")
    assert strategy_js.status_code == 200
    assert "DashboardStrategy" in strategy_js.text
    assert "function renderPlan" in strategy_js.text
    assert "function renderCandidates" in strategy_js.text

    operations_js = client.get("/static/dashboard_operations.js")
    assert operations_js.status_code == 200
    assert "DashboardOperations" in operations_js.text
    assert "function renderSummaries" in operations_js.text
    assert "function renderPriorityActions" in operations_js.text

    api_js = client.get("/static/api.js")
    assert api_js.status_code == 200
    assert "/dashboard/summary" in api_js.text
    assert "/portfolio/rebalance-plan" in api_js.text
    assert "/journal/plans/latest" in api_js.text
    assert "/research/strategies/" in api_js.text

    components_js = client.get("/static/components.js")
    assert components_js.status_code == 200
    assert "function renderCurve" in components_js.text
    assert "function statusTone" in components_js.text

    css = client.get("/static/dashboard.css")
    assert css.status_code == 200
    assert "--accent" in css.text

    strategy_page = client.get("/dashboard/strategies/strategy_a_etf_rotation")
    assert strategy_page.status_code == 200
    assert "策略详情" in strategy_page.text
    assert "策略画像" in strategy_page.text
    assert "今日落地情况" in strategy_page.text
    assert "账户影响快照" in strategy_page.text

    account_page = client.get("/dashboard/accounts/total")
    assert account_page.status_code == 200
    assert "账户详情" in account_page.text
    assert "账户执行链路" in account_page.text
    assert "账户策略暴露" in account_page.text

    research_page = client.get("/dashboard/research")
    assert research_page.status_code == 200
    assert "研究总览与策略筛选" in research_page.text
    assert "当前权重" in research_page.text
    assert "研究结论 vs 今日计划 vs 当前持仓" in research_page.text
    assert "人工审批与最近动作" in research_page.text
    assert "策略链路时间线" in research_page.text
    assert "策略推进清单" in research_page.text

    operations_page = client.get("/dashboard/operations")
    assert operations_page.status_code == 200
    assert "交易计划、总结与归档" in operations_page.text
    assert "执行质量与上线状态" in operations_page.text
    assert "事件回放" in operations_page.text

    journal_page = client.get("/dashboard/journal")
    assert journal_page.status_code == 200
    assert "每日计划与总结归档" in journal_page.text
    assert "今日日报" in journal_page.text
    assert "近 7 日日报时间线" in journal_page.text
    assert "归档缺口" in journal_page.text
    assert "日报详情预览" in journal_page.text
    assert "导出 Markdown" in journal_page.text
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "API.journalPlansLatest" in journal_js.text
    assert "API.journalSummariesLatest" in journal_js.text
    assert "API.journalDaily" in journal_js.text
    assert "API.journalMarkdownLatest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
    assert "as_of" in payload
    assert "overview" in payload
    assert "assets" in payload
    assert "accounts" in payload
    assert "strategies" in payload
    assert "candidates" in payload
    assert "trading_plan" in payload
    assert "journal" in payload
    assert "summaries" in payload
    assert "details" in payload
    assert "total" in payload["accounts"]
    assert "CN" in payload["accounts"]
    assert "nav_curve" in payload["accounts"]["total"]
    assert "top_candidates" in payload["candidates"]
    assert "pending_approvals" in payload["trading_plan"]
    assert "recent_approvals" in payload["trading_plan"]
    assert "latest_plan" in payload["journal"]
    assert "latest_summary" in payload["journal"]
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]
    assert "daily" in payload["summaries"]
    assert "weekly" in payload["summaries"]
    assert "live_acceptance" in payload["details"]
    assert "recent_orders" in payload["details"]
    assert "label" in payload["accounts"]["total"]
    assert "nav" in payload["accounts"]["total"]
    assert "position_value" in payload["accounts"]["total"]
    assert "cash_weight" in payload["accounts"]["total"]
    assert "plan_items" in payload["accounts"]["total"]
    for item in payload["details"]["execution_gate"].get("reasons", []):
        assert "type" in item
        assert "detail" in item


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 7
    assert "correlation_matrix" in candidate_scorecard.json()
    assert "reject_summary" in candidate_scorecard.json()
    assert "verdict_groups" in candidate_scorecard.json()

    candidate_detail = client.get("/research/strategies/strategy_d_mean_reversion", params={"as_of": "2026-03-08"})
    assert candidate_detail.status_code == 200
    assert candidate_detail.json()["strategy_id"] == "strategy_d_mean_reversion"


def test_trading_journal_endpoints():
    generated_plan = client.post("/journal/plans/generate", params={"as_of": "2026-03-08"})
    assert generated_plan.status_code == 200
    assert "headline" in generated_plan.json()

    latest_plan = client.get("/journal/plans/latest")
    assert latest_plan.status_code == 200
    assert "status" in latest_plan.json()
    assert latest_plan.json()["account"] == "total"

    cn_plan = client.get("/journal/plans/latest", params={"account": "CN", "as_of": "2026-03-08"})
    assert cn_plan.status_code == 200
    assert cn_plan.json()["account"] == "CN"

    generated_summary = client.post("/journal/summaries/generate", params={"as_of": "2026-03-08"})
    assert generated_summary.status_code == 200
    assert "highlights" in generated_summary.json()

    latest_summary = client.get("/journal/summaries/latest")
    assert latest_summary.status_code == 200
    assert "headline" in latest_summary.json()


def test_execution_run_endpoint():
    response = client.post("/execution/run", json={})
    assert response.status_code == 200
    payload = response.json()
    assert payload["signal_count"] >= 3
    assert payload["intent_count"] >= 3
    assert "submitted_orders" in payload
    assert "failed_orders" in payload
    assert "approval_count" in payload
    assert "gate" in payload


def test_execution_run_can_enforce_gate():
    original_diagnostics = app_state.adapter_factory.broker_diagnostics
    original_validate = app_state.adapter_factory.validate_futu_connection
    app_state.adapter_factory.broker_diagnostics = lambda: {"backend": "futu", "healthy": False, "detail": "down"}
    app_state.adapter_factory.validate_futu_connection = lambda: {
        "backend": "futu",
        "healthy": False,
        "detail": "failed",
        "checks": {
            "quote": {"status": "failed", "detail": "down"},
            "trade": {"status": "failed", "detail": "down"},
        },
    }
    try:
        response = client.post("/execution/run", json={"enforce_gate": True})
    finally:
        app_state.adapter_factory.broker_diagnostics = original_diagnostics
        app_state.adapter_factory.validate_futu_connection = original_validate
    assert response.status_code == 200
    payload = response.json()
    assert payload["gate"]["should_block"] is True
