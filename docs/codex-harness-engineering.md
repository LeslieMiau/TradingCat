# Codex Harness Engineering

> 日期：2026-03-28  
> 目标：把这台本地受控 Mac mini 上的 Codex harness 调整为“普通开发动作尽量不断流，只在危险或敏感操作时打断”。

## 总结

这次实现把 harness 明确分成两层：

1. **官方 baseline**：以 OpenAI 当前 Codex 文档为准，`sandbox + approval policy` 是主安全边界，`rules` 是稳定的主策略层，`hooks` 只是辅助层。
2. **本机 trusted-host 偏离**：为了让本地开发长时间不断流，默认保留 `workspace-write + network_access = true`，并把 `approval_policy` 改成 granular，只在真正高风险动作上停下来。

仓库里现在提供了一套可安装的 harness bundle：

- [scripts/codex_harness/config.toml](/Users/miau/Documents/TradingCat/scripts/codex_harness/config.toml)
- [scripts/codex_harness/default.rules](/Users/miau/Documents/TradingCat/scripts/codex_harness/default.rules)
- [scripts/codex_harness/hooks.json](/Users/miau/Documents/TradingCat/scripts/codex_harness/hooks.json)
- [scripts/codex_harness/pre_tool_use_guard.py](/Users/miau/Documents/TradingCat/scripts/codex_harness/pre_tool_use_guard.py)
- [scripts/codex_harness/scan_secrets.sh](/Users/miau/Documents/TradingCat/scripts/codex_harness/scan_secrets.sh)
- [scripts/codex_harness/AGENTS.md](/Users/miau/Documents/TradingCat/scripts/codex_harness/AGENTS.md)
- [scripts/codex_harness/tradingcat.repo.config.toml](/Users/miau/Documents/TradingCat/scripts/codex_harness/tradingcat.repo.config.toml)
- [scripts/codex_harness/install.sh](/Users/miau/Documents/TradingCat/scripts/codex_harness/install.sh)

当前这次会话运行在 workspace-only 沙箱里，无法直接写 `~/.codex` 或 repo 的 `.codex/` 保护路径，所以目标状态以安装 bundle 的方式落地。

## 官方 baseline

以下判断直接基于 OpenAI 当前 Codex 文档：

- **主安全控制是 sandbox 和 approval policy**。官方把这两层定义为主要安全机制，不建议靠 hooks 取代。
- **`rules` 适合做主策略层**。官方 `rules` 支持稳定的 `allow` / `prompt` / `forbidden`，并支持 `codex execpolicy check` 验证。
- **`hooks` 只能当辅助层**。`features.codex_hooks` 目前仍是 under development；`PreToolUse` 现在只可靠拦截 Bash，而且 `ask`/`allow` 不能当主安全机制。
- **全局 `AGENTS.md` 应该短、通用、偏个人默认**。repo-specific 的工作流、验证步骤、业务边界应该留在仓库自己的 `AGENTS.md`。
- **profiles 适合保存少量有意义的 preset**，而不是把同一套权限换名字重复声明。

## 本机 trusted-host 偏离

以下项目不是通用企业默认，而是为了满足“本地 trusted Mac mini 上长时间高自治运行”而做的有意识偏离：

- **默认 `workspace-write + network_access = true`**  
  原因：测试、构建、依赖安装、联网查询不应该频繁停住。  
  依据：这是针对本机受控环境的运行偏好，不是官方默认。

- **默认 `approval_policy` 改成 granular，而不是 `never`**  
  原因：`never` 无法只在危险/敏感动作时停下来；granular 才能做到“普通开发动作不断流，高风险动作单独打断”。  
  依据：官方 approval policy 文档明确支持 granular 对象，并把它作为 `never` 与 `on-request` 之间的中间层。

- **默认模型切到 `gpt-5-codex`**  
  原因：官方把它定位为 Codex / agentic coding 优化模型，更适合作为本机默认编码模型。  
  依据：OpenAI 模型文档。

- **保留一个 `deep` profile 使用 `gpt-5.4`**  
  原因：更复杂的架构分析、审阅、长推理任务仍然可能更适合更强泛化模型。  
  依据：这是本机工作流选择，不是官方唯一推荐。

- **移除旧的固定 compaction override**  
  原因：旧值是按 `gpt-5.4` 的上下文窗口调的；当默认模型切到 `gpt-5-codex` 后，再保留那个固定阈值不再是安全的全局默认。  
  依据：本机配置一致性判断。

## 已实现的结构

### 1. 全局 config 模板

[scripts/codex_harness/config.toml](/Users/miau/Documents/TradingCat/scripts/codex_harness/config.toml) 做了这些调整：

- 默认 `sandbox_mode = "workspace-write"`
- 默认 `network_access = true`
- 用 granular approval 替代 `never`
- 只保留少量确有用途的 feature 和 profile
- 默认模型切到 `gpt-5-codex`

granular 选择如下：

```toml
approval_policy = { granular = { sandbox_approval = true, rules = true, mcp_elicitations = true, request_permissions = true, skill_approval = false } }
```

判断依据：

- `sandbox_approval = true`：离开沙箱仍然应当打断。
- `rules = true`：命中 `prompt` 规则时应当停下来。
- `mcp_elicitations = true` / `request_permissions = true`：外部系统和显式提权仍然需要确认。
- `skill_approval = false`：这是本机高自治偏离项，默认信任已安装技能以减少无意义打断。

### 2. Rules 作为主策略层

[scripts/codex_harness/default.rules](/Users/miau/Documents/TradingCat/scripts/codex_harness/default.rules) 承接固定前缀、明确可判定的高风险命令：

- `forbidden`
  - `git reset --hard`
  - `git clean -f` 及常见强删变体
  - `diskutil eraseDisk`
  - 常见 `mkfs` / `newfs` 命令
  - `shutdown` / `reboot` / `halt` / `poweroff`
- `prompt`
  - `sudo ...`
  - `git branch -D ...`
  - `killall ...`
  - `pkill -9 ...`

修改原因：

- 这些命令是稳定前缀，适合用 rules 表达。
- rules 有明确的 `prompt` / `forbidden` 语义，并且可以用 `execpolicy check` 做静态验证。
- 这比把高风险命令全部塞进 hooks 正则更稳定，也更符合官方推荐。

### 3. Hooks 退到补洞层

[scripts/codex_harness/pre_tool_use_guard.py](/Users/miau/Documents/TradingCat/scripts/codex_harness/pre_tool_use_guard.py) 和 [scripts/codex_harness/hooks.json](/Users/miau/Documents/TradingCat/scripts/codex_harness/hooks.json) 只保留 deny-only 的 Bash guard：

- `curl|bash` / `wget|bash`
- `git push ... --force` / `-f`
- `rm` 指向 `/`、`~`、`..`、`*` 这类过宽目标
- `git commit` 前调用 [scripts/codex_harness/scan_secrets.sh](/Users/miau/Documents/TradingCat/scripts/codex_harness/scan_secrets.sh)

修改原因：

- 这些情形要么 flag 位置不固定，要么更适合看完整 Bash 文本。
- 当前 Codex hooks 对 Bash deny 有用，但不适合承接 `ask` 或完整安全边界。
- 因此 hooks 现在只负责“rules 不擅长表达，但必须补上”的空白。

### 4. 全局 AGENTS 恢复成个人默认层

[scripts/codex_harness/AGENTS.md](/Users/miau/Documents/TradingCat/scripts/codex_harness/AGENTS.md) 只保留：

- 这台 Mac mini 是 trusted 本地环境
- 默认倾向自主执行
- repo-specific workflow 以仓库 `AGENTS.md` / `.codex/config.toml` 为准
- destructive / privileged / real-world side effects 要尊重 sandbox、rules、repo policy

修改原因：

- `PLAN.json` / `PROGRESS.md` / `init.sh` / “每 session 只做一个 feature” 这类要求属于项目流程，不应该写成全局 Codex 信条。
- TradingCat 这类业务边界已经在仓库 [AGENTS.md](/Users/miau/Documents/TradingCat/AGENTS.md) 里定义，继续塞进全局层只会造成重复和冲突。

### 5. TradingCat repo config 目标状态

[scripts/codex_harness/tradingcat.repo.config.toml](/Users/miau/Documents/TradingCat/scripts/codex_harness/tradingcat.repo.config.toml) 是这个仓库 `.codex/config.toml` 的目标状态：

- `tradingcat_review`: 只读、安静审阅
- `tradingcat_guarded`: 对交易敏感工作提供更严格的 `on-request + no network`

修改原因：

- 原来 repo 顶层的 `approval_policy = "never"` 与 `sandbox_mode = "workspace-write"` 会直接覆盖新的全局策略，导致全局 harness 失效。
- 目标状态是 repo 默认继承全局 harness，只有显式选 profile 时才启用更严格的项目策略。

## 判断依据表

| Area | 最终选择 | 原因 | 判断依据 |
|------|----------|------|----------|
| Approval policy | `granular` | 只在危险/敏感操作时打断 | OpenAI 官方文档 + 本机目标 |
| Main safety layer | `rules` | 稳定、可测试、支持 prompt/forbidden | OpenAI 官方文档 |
| Hooks | deny-only 补洞 | Bash only，under development，不适合做主边界 | OpenAI 官方文档 |
| Global AGENTS | 只放个人默认 | repo workflow 不该上升为全局规则 | OpenAI 官方文档 + 本机现状观察 |
| Default model | `gpt-5-codex` | 更贴近 Codex 编码场景 | OpenAI 官方文档 |
| Network access | `workspace-write + true` | 避免正常联网开发频繁停顿 | 本机 trusted-host 偏离 |
| Repo `.codex/config.toml` | 仅保留 stricter profiles | 避免覆盖全局 harness | 本机现状观察 |
| Secrets scan | commit 前 deny | 提交凭证属于高敏感动作 | 本机现状观察 + 安全常识 |

## 使用方式

安装全局 bundle 并同步这个仓库的 `.codex/config.toml` 目标状态：

```bash
bash scripts/codex_harness/install.sh
```

安装后重启 Codex，让新的全局 `config.toml`、`rules`、`hooks` 和 `AGENTS.md` 生效。

项目内更严格地运行：

```bash
codex --profile tradingcat_review
codex --profile tradingcat_guarded
```

## 参考依据

- [OpenAI Codex: Best practices](https://developers.openai.com/codex/learn/best-practices)
- [OpenAI Codex: Config basics](https://developers.openai.com/codex/config-basic)
- [OpenAI Codex: Advanced configuration](https://developers.openai.com/codex/config-advanced)
- [OpenAI Codex: Configuration reference](https://developers.openai.com/codex/config-reference)
- [OpenAI Codex: Agent approvals and security](https://developers.openai.com/codex/agent-approvals-security)
- [OpenAI Codex: Rules](https://developers.openai.com/codex/rules)
- [OpenAI Codex: Hooks](https://developers.openai.com/codex/hooks)
- [OpenAI Models: GPT-5-Codex](https://developers.openai.com/api/docs/models/gpt-5-codex)
