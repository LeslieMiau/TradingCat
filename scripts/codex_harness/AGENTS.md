# Codex Long-Running Harness

每次 session / compact / resume 后都必须先恢复状态，再开始工作。

强制启动序列：
1. `pwd`
2. `git log --oneline -20`
3. 阅读 `PROGRESS.md`
4. 阅读 `PLAN.json`
5. 运行 `init.sh`
6. 选择下一个未完成 feature 开始工作

外部状态文件：
- `PLAN.json`：任务规格，默认只能修改 `passes` 字段，不得删除或改写 `description` / `steps`
- `PROGRESS.md`：追加式进度日志，记录已做工作、决定原因、剩余问题

行为约束：
- 每个 session 只做一个 feature，避免上下文耗尽后质量崩溃
- 开始新 feature 前，先确认当前功能和测试基线正常
- 不允许通过删除测试、削弱断言、跳过验证来“完成”任务
- 每个 feature 完成后都要用 `git commit` 留检查点
- 如果环境验证失败，先修复环境或记录阻塞，再继续编码
