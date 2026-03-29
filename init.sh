#!/usr/bin/env bash
# init.sh — Codex/Claude Code session 启动脚本
# 每次 session 开始时运行：启动环境 + 验证基本功能
# 注意：不使用 set -e，每步独立报告状态，避免局部失败阻断整个启动

cd "$(dirname "$0")"
ERRORS=0

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
if curl -sS -o /dev/null -w '' http://127.0.0.1:8000/preflight 2>/dev/null; then
  echo "服务已在运行"
else
  echo "启动 dev server..."
  TRADINGCAT_RELOAD=true ./scripts/run_local.sh &
  sleep 3
fi

echo "=== 4. 健康检查 ==="
HEALTH=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/preflight 2>/dev/null || echo "000")
if [ "$HEALTH" = "200" ]; then
  echo "✅ 服务正常 (HTTP $HEALTH)"
else
  echo "⚠️  服务异常 (HTTP $HEALTH)"
  ERRORS=$((ERRORS+1))
fi

echo "=== 初始化完成 (问题数: $ERRORS) ==="
exit 0
