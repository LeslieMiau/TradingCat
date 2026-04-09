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
};
