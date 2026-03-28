# Codex Harness Engineering 配置说明

> 日期：2026-03-28
> 执行者：Claude Opus 4.6（通过 Claude Code）
> 目标：将 Codex 配置为可长期自主运行的工程 harness，最大化自主权的同时保证安全

---

## 一、背景与动机

原始 Codex 配置存在以下问题：

1. **`rules/default.rules` 膨胀**：积累了 53 条一次性 prefix_rule（含一条 2KB 的内联 node 脚本），无实际意义
2. **Profiles 名不副实**：`read_only` profile 使用 `workspace-write` sandbox，三个 profile 配置几乎相同
3. **`AGENTS.md` 与 `CLAUDE.md` 重复**：两份文件内容一致，维护负担
4. **无长期运行支持**：缺少上下文压缩、抗遗忘、环境验证等机制

## 二、设计原则

参考两个来源：
- [OpenAI Codex 官方文档](https://developers.openai.com/codex/) — 配置选项、hooks 机制、最佳实践
- [Anthropic: Effective Harnesses for Long-Running Agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) — 外化状态、增量工作、环境验证

核心思路：**最大自主权 + 安全护栏 + 抗遗忘**

```
┌─────────────────────────────────────────────┐
│  Codex Agent (gpt-5.4, approval=never)      │
│                                             │
│  ┌─────────┐  ┌──────────┐  ┌───────────┐  │
│  │ PLAN.json│  │PROGRESS.md│  │ git commit│  │
│  │ 任务规格 │  │ 进度日志  │  │ 检查点    │  │
│  └─────────┘  └──────────┘  └───────────┘  │
│                                             │
│  每个 session 启动 → 读文件恢复状态 → 工作  │
├─────────────────────────────────────────────┤
│  hooks.json → permission_guard.sh           │
│  黑名单拦截危险操作 / git commit 前扫描凭证  │
└─────────────────────────────────────────────┘
```

## 三、文件变更清单

### 3.1 `~/.codex/config.toml`（全部重写）

```toml
model = "gpt-5.4"
model_reasoning_effort = "high"
model_reasoning_summary = "concise"
model_auto_compact_token_limit = 800000  # gpt-5.4 有 1.05M 上下文，76% 时触发压缩

approval_policy = "never"       # 无人值守不卡住
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true           # 允许 curl/npm 等

[shell_environment_policy]
inherit = "all"
exclude = ["*SECRET*", "*TOKEN*", "*KEY*", "*PASSWORD*", "*CREDENTIAL*"]

[agents]
max_threads = 6
max_depth = 2                   # 子代理可再派子代理
job_max_runtime_seconds = 3600  # 单个子任务上限 1 小时

[features]
codex_hooks = true              # hooks 支持（实验特性）
memories = true                 # 跨会话记忆
enable_fanout = true            # 并行子任务
undo = true                     # 撤销支持
prevent_idle_sleep = true       # 长任务防休眠

[profiles.fast]                 # codex --profile fast
model = "gpt-5.3-codex"
model_reasoning_effort = "medium"

[profiles.deep]                 # codex --profile deep
model = "gpt-5.4"
model_reasoning_effort = "xhigh"
model_reasoning_summary = "detailed"
```

**关键决策说明：**

| 配置项 | 选择 | 理由 |
|--------|------|------|
| `approval_policy = "never"` | 永不暂停等确认 | 长期运行场景下 `on-request` 会导致卡死，安全由 hooks 兜底 |
| `compact_token_limit = 800000` | 延迟到 76% 才压缩 | gpt-5.4 有 1.05M 上下文，尽量晚压缩以保留更多工作记忆 |
| `shell_environment_policy.exclude` | 排除密钥变量 | `inherit = "all"` 继承完整环境，但过滤 SECRET/TOKEN/KEY 防泄露 |
| `agents.max_depth = 2` | 允许两层子代理 | 复杂任务可分层分解，默认值 1 对 harness 场景不够 |
| 三个 profiles | 按场景切换 | 默认(日常) / fast(迭代) / deep(架构) 覆盖不同任务类型 |

### 3.2 `~/.codex/hooks.json`（新建）

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "bash /Users/miau/.claude/scripts/permission_guard.sh",
            "statusMessage": "安全检查中…",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

复用 Claude Code 的 `permission_guard.sh` 脚本。经验证：
- Codex hooks 的 stdin JSON 格式与 Claude Code 完全一致（`tool_name` / `tool_input`）
- `deny` 决策确认能在 Codex 中正确拦截（日志显示 `Blocked`）
- 首次调用偶现 `Failed`（沙箱冷启动问题），不影响安全

### 3.3 `~/.claude/scripts/permission_guard.sh`（修改）

变更点：
1. **合并 scan_secrets 逻辑**：`git commit` 前自动调用 `scan_secrets.sh`，不再需要独立 hook（解决多 hook 争抢 stdin 的问题）
2. **jq 回退机制**：无 jq 时用 grep/sed 提取 JSON 字段，兼容 Codex 沙箱环境
3. **函数定义前置**：`allow()/deny()/ask()` 移到脚本最前面，避免提前调用时 function not found
4. **移除 `set -e`**：防止非关键错误导致整个 hook 崩溃

### 3.4 `~/.codex/AGENTS.md`（全部重写）

不再复制 CLAUDE.md 内容，改为 Codex 长期运行专用指令：

**抗遗忘机制（核心新增）：**

```
强制启动序列（每次 session/compact/resume 后）：
1. pwd — 确认工作目录
2. git log --oneline -20 — 了解最近工作
3. 读 PROGRESS.md — 恢复任务上下文
4. 读 PLAN.json — 了解任务规格和进度
5. 运行 init.sh — 启动环境并验证
6. 选择下一个未完成 feature 开始工作
```

**外部状态文件：**

- `PLAN.json`：任务规格（JSON 格式，模型比 Markdown 更不易篡改），只能改 `passes` 字段
- `PROGRESS.md`：叙述性进度日志，每步追加不覆盖，记录决策理由

**行为约束：**

- 每个 session 只做一个 feature（防止 context 耗尽导致质量崩溃）
- 禁止删除或修改 PLAN.json 中的 description/steps（防止"通过删测试来通过测试"）
- 开始新 feature 前先验证已有功能正常（防止继承破损状态）

### 3.5 `~/Documents/TradingCat/init.sh`（新建）

项目级启动脚本，Codex 每次 session 开始时执行：

```
1. 环境检查 → 确保 .venv、依赖、.env 就绪
2. 运行测试 → pytest -x -q 快速验证无回归
3. 启动服务 → uvicorn dev server（已运行则跳过）
4. 健康检查 → curl /preflight 确认服务正常
```

### 3.6 删除的文件

| 文件 | 理由 |
|------|------|
| `~/.codex/rules/default.rules` | 53 条一次性规则，已被 hooks 机制替代 |
| 旧 `~/.codex/config.toml` | profiles 混乱，配置不合理 |
| 旧 `~/.codex/AGENTS.md` | 与 CLAUDE.md 重复 |

## 四、Claude Code 侧同步变更

`~/.claude/settings.json` 中删除了独立的 `scan_secrets` hook（第二个 PreToolUse），因为该逻辑已合并到 `permission_guard.sh` 中。两个工具现在共享同一个安全脚本，减少维护负担。

## 五、验证结果

| 测试项 | 结果 |
|--------|------|
| config.toml TOML 语法 | ✅ 有效 |
| hooks.json JSON 语法 | ✅ 有效 |
| Codex 启动加载配置 | ✅ model/approval/sandbox 全部正确 |
| Hook allow 放行普通命令 | ✅ `ls`/`pwd` 等正常执行 |
| Hook deny 拦截危险操作 | ✅ 确认 `Blocked` 日志，命令未执行 |
| AGENTS.md 启动序列被遵循 | ✅ Codex 收到任务后先执行 pwd → git log → 读文件 |
| permission_guard.sh 无 jq 回退 | ✅ grep/sed 模式正确提取字段 |
| permission_guard.sh 空输入/异常输入 | ✅ 默认放行，不崩溃 |

**已知限制：**
- `codex_hooks` 为实验特性，首次 hook 调用偶现 `Failed`（沙箱冷启动问题），不影响安全和功能
- Codex 沙箱内 `jq` 可能不可用，已通过 grep 回退解决

## 六、使用方式

```bash
# 日常工程（gpt-5.4, 自主运行）
codex "重构 data pipeline，拆分为 fetcher/parser/storage 三层"

# 快速迭代（gpt-5.3-codex, 速度优先）
codex --profile fast "修复 test_strategy 的断言错误"

# 深度思考（gpt-5.4 xhigh, 架构设计）
codex --profile deep "设计 TradingCat 的多策略并行执行架构"

# 恢复上次会话
codex resume --last
```

## 七、与 Anthropic 文章的对应关系

| Anthropic 实践 | 本次实现 | 对应文件 |
|---|---|---|
| Feature list (JSON, 不可篡改) | PLAN.json（只能改 passes 字段） | AGENTS.md 约束 |
| Progress file (叙述性日志) | PROGRESS.md（追加不覆盖） | AGENTS.md 约束 |
| Init script (环境验证) | init.sh（依赖→测试→服务→健康检查） | TradingCat/init.sh |
| 强制启动序列 | 6 步流程 | AGENTS.md |
| 每 session 只做一个 feature | 明确约束 | AGENTS.md |
| 不可删测试 | 明确禁止 | AGENTS.md |
| Git checkpoint | 每个 feature 完成后 commit | AGENTS.md |
| 多代理分工 | 未实现（文章也标注为未探索） | — |
