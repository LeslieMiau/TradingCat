## Session 2026-03-28
- 启动序列完成：读取最近提交，当前无既有 `PLAN.json`/`PROGRESS.md`，并执行了 `./init.sh`。
- 基线状态：`./init.sh` 失败于 `tests/test_api.py::test_dashboard_page_and_assets`，现有断言仍引用旧文案“今日计划与总结”。
- 决策：本 session 先执行 `handoff-frontend-refactor.md` 的首个高优先级 feature：共享组件层 + API 注册表 + 页面脚本接入。
- 规格疑问：handoff 前文写“仅修改 static/，不改模板”，但 Task 1.3 明确要求更新 `templates/` 脚本加载；为保证新共享脚本可用，本次将采用更安全且可逆的方案，按 Task 1.3 接入模板，并在这里保留记录。
- 完成 `static/api.js` 与 `static/components.js`，统一了 `renderCurve`、`statusTone`，并让各页面改为通过 `API.*` 访问接口。
- 更新 6 个模板的脚本加载顺序，接入 `api.js` 与 `components.js`；同步修正 `tests/test_api.py` 中已经落后的页面文案与静态资源断言。
- 验证：`source .venv/bin/activate && pytest tests/test_api.py` 通过（11 passed）；`./init.sh` 通过（115 passed），服务可启动。
- 环境备注：`./init.sh` 启动服务时仍出现 Futu SDK 日志目录权限告警，但系统已按现有逻辑回退到 simulated adapter，不影响本次前端 refactor 验证。
- 提交备注：尝试执行 `git add` 时受到当前沙箱限制，报错 `.git/index.lock: Operation not permitted`，因此本 session 无法在此环境内完成 stage / commit。
