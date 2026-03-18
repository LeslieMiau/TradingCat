response = client.get("/research/backtests/compare", params={"left_id": left_id, "right_id": right_id})
    assert response.status_code == 200
    compared = response.json()
    assert "same_inputs" in compared
    assert "input_diff" in compared
    assert "metric_diff" in compared


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
    assert allocation_summary.json()["count"] == 3


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
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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


def test_research_scorecard_and_strategy_detail_endpoints():
    scorecard = client.post("/research/scorecard/run", params={"as_of": "2026-03-08"})
    assert scorecard.status_code == 200
    assert "rows" in scorecard.json()
    assert len(scorecard.json()["rows"]) == 3

    detail = client.get("/research/strategies/strategy_a_etf_rotation", params={"as_of": "2026-03-08"})
    assert detail.status_code == 200
    payload = detail.json()
assert response.status_code == 200
    payload = response.json()
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "ready" in payload
    assert "should_block" in payload
    assert "reasons" in payload


def test_dashboard_page_and_assets():
    page = client.get("/dashboard")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "TradingCat Dashboard" in page.text
    assert "账户、策略、计划与总结" in page.text
    assert "今日计划与总结" in page.text
    assert "计划分段" in page.text
    assert "总结分段" in page.text
    assert "四账户对照" in page.text
    assert "资金使用率与计划消耗" in page.text
    assert "四账户风险快照" in page.text
    assert "收益来源快照" in page.text
    assert "持仓集中度 Top" in page.text
    assert "配置偏离与再平衡建议" in page.text
    assert "市场预算对照" in page.text
    assert "计划按策略拆分" in page.text
    assert "策略表现 Top" in page.text
    assert "策略资金占用 Top" in page.text
    assert "策略执行落地 Top" in page.text
    assert "账户-策略矩阵" in page.text
    assert "计划按市场拆分" in page.text
    assert "研究分组总览" in page.text
    assert "今日方向概览" in page.text
    assert "计划名义金额 Top" in page.text
    assert "计划持仓偏差 Top" in page.text
    assert "计划正文" in page.text
    assert "今日信号漏斗" in page.text
    assert "今日卡点摘要" in page.text
    assert "今日优先动作" in page.text
    assert "今日交易计划" in page.text
    assert "每日总结与阻塞项" in page.text
    assert "总结正文" in page.text
    assert "全局阻塞与最近事件" in page.text
    assert "最近联调快照" in page.text
    assert "数据与联调健康" in page.text
    assert "上线推进进度" in page.text
    assert "执行与审批队列" in page.text
    assert "最近成交与验证单" in page.text
    assert "审批与订单时效" in page.text
    assert "/static/dashboard.css" in page.text
    assert "/static/dashboard.js" in page.text

    js = client.get("/static/dashboard.js")
    assert js.status_code == 200
    assert "/dashboard/summary" in js.text
    assert "/portfolio/rebalance-plan" in js.text

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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text
    assert "/journal/daily" in journal_js.text
    assert "/journal/markdown/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
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
    assert "计划归档" in journal_page.text
    assert "总结归档" in journal_page.text

    journal_js = client.get("/static/journal.js")
    assert journal_js.status_code == 200
    assert "/journal/plans/latest" in journal_js.text
    assert "/journal/summaries/latest" in journal_js.text


def test_dashboard_summary_endpoint():
    response = client.get("/dashboard/summary")
    assert response.status_code == 200
    payload = response.json()
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
    assert "recent_plans" in payload["journal"]
    assert "recent_summaries" in payload["journal"]


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
    assert len(candidate_scorecard.json()["rows"]) == 5
    assert "correlation_matrix" in candidate_scorecard.json()
    assert "reject_summary" in candidate_scorecard.json()
    assert "verdict_groups" in candidate_scorecard.json()

    candidate_detail = client.get("/research/strategies/strategy_d_mean_reversion", params={"as_of": "2026-03-08"})
    assert candidate_detail.status_code == 200
    assert candidate_detail.json()["strategy_id"] == "strategy_d_mean_reversion"
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
payload = detail.json()
    assert payload["strategy_id"] == "strategy_a_etf_rotation"
    assert "metadata" in payload
    assert "nav_curve" in payload
    assert "benchmark" in payload
    assert "yearly_performance" in payload
    assert "recommendation" in payload

    candidate_scorecard = client.post("/research/candidates/scorecard", params={"as_of": "2026-03-08"})
    assert candidate_scorecard.status_code == 200
    assert len(candidate_scorecard.json()["rows"]) == 5
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
