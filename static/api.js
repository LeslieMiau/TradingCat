const API = {
  /* ── Dashboard & Portfolio ── */
  dashboardSummary: "/dashboard/summary",
  portfolioRebalancePlan: "/portfolio/rebalance-plan",
  portfolioReconcile: "/portfolio/reconcile",

  /* ── Orders ── */
  orders: "/orders",
  orderCancel: (id) => `/orders/${encodeURIComponent(id)}/cancel`,
  ordersCancelOpen: "/orders/cancel-open",
  ordersManual: "/orders/manual",
  ordersTriggers: "/orders/triggers",

  /* ── Kill Switch ── */
  killSwitch: "/kill-switch",
  killSwitchToggle: (enabled, reason) => `/kill-switch?enabled=${encodeURIComponent(String(enabled))}&reason=${encodeURIComponent(reason)}`,

  /* ── Journal ── */
  journalPlans: (account) => account ? `/journal/plans?account=${encodeURIComponent(account)}` : "/journal/plans",
  journalPlansLatest: (account) => account ? `/journal/plans/latest?account=${encodeURIComponent(account)}` : "/journal/plans/latest",
  journalPlansGenerate: "/journal/plans/generate",
  journalSummaries: (account) => account ? `/journal/summaries?account=${encodeURIComponent(account)}` : "/journal/summaries",
  journalSummariesLatest: (account) => account ? `/journal/summaries/latest?account=${encodeURIComponent(account)}` : "/journal/summaries/latest",
  journalSummariesGenerate: "/journal/summaries/generate",
  journalDaily: (account) => `/journal/daily?account=${encodeURIComponent(account)}`,
  journalMarkdownLatest: (account) => `/journal/markdown/latest?account=${encodeURIComponent(account)}`,

  /* ── Approvals ── */
  approvals: "/approvals",
  approvalApprove: (id) => `/approvals/${encodeURIComponent(id)}/approve`,
  approvalReject: (id) => `/approvals/${encodeURIComponent(id)}/reject`,
  approvalExpireStale: "/approvals/expire-stale",

  /* ── Execution ── */
  executionPreview: "/execution/preview",
  executionRun: "/execution/run",
  executionGate: "/execution/gate",
  executionQuality: "/execution/quality",

  /* ── Operations ── */
  opsLiveAcceptance: "/ops/live-acceptance",
  opsRollout: "/ops/rollout",
  opsRolloutPromote: "/ops/rollout/promote",
  opsExecutionMetrics: "/ops/execution-metrics",
  opsIncidentsReplay: (windowDays = 7) => `/ops/incidents/replay?window_days=${encodeURIComponent(windowDays)}`,
  opsTca: "/ops/tca",
  opsRiskConfig: "/ops/risk/config",
  opsEvaluateTriggers: "/ops/evaluate-triggers",
  opsAcceptanceEvidenceCapture: "/ops/acceptance/evidence/capture",
  opsAcceptanceEvidenceTimeline: (windowDays = 42) => `/ops/acceptance/evidence/timeline?window_days=${encodeURIComponent(windowDays)}`,

  /* ── Research ── */
  researchStrategies: (id) => `/research/strategies/${encodeURIComponent(id)}`,
  researchScorecard: "/research/scorecard/run",
  researchCandidatesScorecard: "/research/candidates/scorecard",
  researchCorrelation: "/research/correlation",
  researchMarketAwareness: "/research/market-awareness",
  researchAlphaRadar: (count = 15) => `/research/alpha-radar?count=${encodeURIComponent(count)}`,
  researchMacroCalendar: (days = 7) => `/research/macro-calendar?days=${encodeURIComponent(days)}`,

  /* ── Signals & Alerts ── */
  signalsToday: "/signals/today",
  alerts: "/alerts",
  alertsSummary: "/alerts/summary",

  /* ── Broker & Data ── */
  brokerStatus: "/broker/status",
  brokerRecover: "/broker/recover",
  dataQuality: (days = 7) => `/data/quality?lookback_days=${encodeURIComponent(days)}`,
  marketSessions: "/market-sessions",

  /* ── Diagnostics ── */
  diagnosticsSummary: "/diagnostics/summary",

  /* ── Quant Research (Phase 1-3) ── */
  quantFeatures: (symbols = "SPY,QQQ", days = 60) => `/research/features?symbols=${encodeURIComponent(symbols)}&days=${encodeURIComponent(days)}`,
  quantFactors: (symbols = "SPY,QQQ", days = 60) => `/research/factors?symbols=${encodeURIComponent(symbols)}&days=${encodeURIComponent(days)}`,
  quantOptimize: (symbols = "SPY,QQQ", method = "risk_parity") => `/research/optimize?symbols=${encodeURIComponent(symbols)}&method=${encodeURIComponent(method)}`,
  quantMLPredict: (symbols = "SPY,QQQ") => `/research/ml/predict?symbols=${encodeURIComponent(symbols)}`,
  quantAlternative: (symbols) => symbols ? `/research/alternative?symbols=${encodeURIComponent(symbols)}` : "/research/alternative",
  quantAIBriefing: "/research/ai/briefing",
  quantAutoResearchRun: "/research/auto-research/run",
  quantAutoResearchLatest: "/research/auto-research/latest",
  quantAttribution: (start, end) => `/research/attribution?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`,

  /* ── Insights ── */
  insightsList: "/insights",
  insightsRun: "/insights/run",
  insightDismiss: (id) => `/insights/${encodeURIComponent(id)}/dismiss`,
  insightAck: (id) => `/insights/${encodeURIComponent(id)}/ack`,
};
