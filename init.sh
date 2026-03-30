#!/usr/bin/env bash
# init.sh — Codex/Claude Code session 启动脚本
# 每次 session 开始时运行：启动环境 + 验证基本功能
# 注意：不使用 set -e，每步独立报告状态，避免局部失败阻断整个启动

cd "$(dirname "$0")"
ERRORS=0
BASE_URL="http://127.0.0.1:8000"
HEALTH_TIMEOUT_SECONDS="${TRADINGCAT_CORE_HEALTH_TIMEOUT_SECONDS:-5}"
HEALTH_LOG="/tmp/tradingcat-core-health.log"

check_core_health() {
  .venv/bin/python -m tradingcat.services.service_health --base-url "$BASE_URL" --timeout "$HEALTH_TIMEOUT_SECONDS"
}

find_tradingcat_server_pid() {
  local repo_root
  local pid
  local cmd
  local cwd
  repo_root="$(pwd)"
  for pid in $(lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null); do
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n1)"
    if echo "$cmd" | grep -q "uvicorn tradingcat.main:app"; then
      echo "$pid"
      return 0
    fi
    if [ "$cwd" = "$repo_root" ] && echo "$cmd" | grep -qi "python"; then
      echo "$pid"
      return 0
    fi
  done
  return 1
}

echo "=== 1. 环境检查 ==="
if [ ! -d .venv ]; then
  echo "创建 virtualenv..."
  python3 -m venv .venv
fi

if ! .venv/bin/python -c "import tradingcat" 2>/dev/null; then
  echo "安装依赖..."
  .venv/bin/python -m pip install -q -e '.[dev]' || { echo "⚠️  依赖安装失败"; ERRORS=$((ERRORS+1)); }
fi

if [ ! -f .env ]; then
  echo "初始化 .env (simulate 模式)..."
  ./scripts/bootstrap_env.sh simulate || { echo "⚠️  .env 初始化失败"; ERRORS=$((ERRORS+1)); }
fi

echo "=== 2. 运行测试 ==="
.venv/bin/pytest tests/ -x -q --tb=short 2>&1 | tail -20
TEST_EXIT=${PIPESTATUS[0]}
if [ "$TEST_EXIT" -ne 0 ]; then
  echo "⚠️  测试失败 (exit=$TEST_EXIT)"
  ERRORS=$((ERRORS+1))
fi

echo "=== 3. 启动服务 ==="
if check_core_health >"$HEALTH_LOG" 2>&1; then
  echo "服务已在运行且 core health 正常"
else
  if PID="$(find_tradingcat_server_pid)"; then
    echo "检测到 8000 端口上的 TradingCat 进程 core health 异常，准备重启 (pid=$PID)..."
    kill "$PID" 2>/dev/null || true
    sleep 2
  elif lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "⚠️  8000 端口被非 TradingCat 进程占用，无法自动重启"
    ERRORS=$((ERRORS+1))
  fi
  if ! lsof -tiTCP:8000 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "启动 dev server..."
    TRADINGCAT_RELOAD=true ./scripts/run_local.sh &
    sleep 5
  fi
fi

echo "=== 4. 健康检查 ==="
if check_core_health >"$HEALTH_LOG" 2>&1; then
  echo "✅ 服务正常 (core endpoints healthy)"
else
  echo "⚠️  服务异常 (core endpoints unhealthy)"
  cat "$HEALTH_LOG"
  ERRORS=$((ERRORS+1))
fi

echo "=== 初始化完成 (问题数: $ERRORS) ==="
exit 0
