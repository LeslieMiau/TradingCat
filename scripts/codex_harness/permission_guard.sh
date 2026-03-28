#!/usr/bin/env bash
# permission_guard.sh — 默认放行权限请求，仅黑名单拦截危险操作
# 适用于 Claude Code (settings.json) 和 Codex (hooks.json)
# 兼容无 jq 环境：优先用 jq，回退到 grep/sed 提取字段

allow() {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","permissionDecisionReason":"'"$1"'"}}'
  exit 0
}

deny() {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"'"$1"'"}}'
  exit 0
}

ask() {
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"ask","permissionDecisionReason":"'"$1"'"}}'
  exit 0
}

INPUT=$(cat)

if [ -z "$INPUT" ]; then
  allow "空输入，默认放行"
fi

if command -v jq &>/dev/null; then
  TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty' 2>/dev/null || echo "")
  COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty' 2>/dev/null || echo "")
  FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty' 2>/dev/null || echo "")
  CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // empty' 2>/dev/null || echo "")
else
  TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name":"[^"]*"' | head -1 | sed 's/"tool_name":"//;s/"//')
  COMMAND=$(echo "$INPUT" | grep -o '"command":"[^"]*"' | head -1 | sed 's/"command":"//;s/"//')
  FILE_PATH=$(echo "$INPUT" | grep -o '"file_path":"[^"]*"' | head -1 | sed 's/"file_path":"//;s/"//')
  CONTENT=""
fi

if [ -z "$TOOL_NAME" ]; then
  allow "无法解析工具名，默认放行"
fi

if [ "$TOOL_NAME" = "Bash" ] && [ -n "$COMMAND" ]; then
  if echo "$COMMAND" | grep -qE 'rm\s+(-[a-zA-Z]*f[a-zA-Z]*\s+|--force\s+)*(\/|~|\$HOME|\.\.)'; then
    deny "拦截: rm 指向根目录/HOME/上级目录，风险极高"
  fi
  if echo "$COMMAND" | grep -qE 'rm\s+-[a-zA-Z]*r[a-zA-Z]*f|rm\s+-[a-zA-Z]*f[a-zA-Z]*r'; then
    TARGET=$(echo "$COMMAND" | grep -oE 'rm\s+-[a-zA-Z]+\s+(.+)' | sed 's/rm\s\+-[a-zA-Z]\+\s\+//')
    if echo "$TARGET" | grep -qE '^\s*(\/|~|\$HOME|\.\.|\*)\s*$'; then
      deny "拦截: rm -rf 目标过于宽泛 ($TARGET)"
    fi
  fi

  if echo "$COMMAND" | grep -qE '^\s*git\s+commit'; then
    if ! bash /Users/miau/.claude/scripts/scan_secrets.sh 2>/dev/null; then
      deny "拦截: scan_secrets 检测到敏感信息"
    fi
  fi

  if echo "$COMMAND" | grep -qE 'git\s+push\s+.*--force|git\s+push\s+-f'; then
    deny "拦截: git push --force 可能覆盖远程历史"
  fi
  if echo "$COMMAND" | grep -qE 'git\s+reset\s+--hard'; then
    deny "拦截: git reset --hard 会丢弃未提交更改"
  fi
  if echo "$COMMAND" | grep -qE 'git\s+clean\s+-[a-zA-Z]*f'; then
    deny "拦截: git clean -f 会删除未跟踪文件"
  fi
  if echo "$COMMAND" | grep -qE 'git\s+checkout\s+--\s+\.'; then
    deny "拦截: git checkout -- . 会丢弃所有工作区修改"
  fi
  if echo "$COMMAND" | grep -qE 'git\s+branch\s+-D'; then
    ask "git branch -D 强制删除分支，请确认"
  fi

  if echo "$COMMAND" | grep -qE '(>|tee|cp|mv|install)\s+(/etc/|/System/|/usr/|/var/)'; then
    deny "拦截: 写入系统关键目录"
  fi

  if echo "$COMMAND" | grep -qE '^\s*sudo\s'; then
    ask "检测到 sudo，请确认是否需要提权"
  fi

  if echo "$COMMAND" | grep -qE 'curl\s.*\|\s*(ba)?sh|wget\s.*\|\s*(ba)?sh'; then
    deny "拦截: 管道执行远程脚本，存在安全风险"
  fi

  if echo "$COMMAND" | grep -qiE '(DROP\s+(TABLE|DATABASE|SCHEMA)|TRUNCATE\s+TABLE|DELETE\s+FROM\s+\S+\s*;)'; then
    deny "拦截: 数据库破坏性操作"
  fi

  if echo "$COMMAND" | grep -qE 'chmod\s+777|chmod\s+-R\s+777'; then
    deny "拦截: chmod 777 权限过于宽松"
  fi
  if echo "$COMMAND" | grep -qE 'chown\s+-R\s+root'; then
    deny "拦截: 批量修改文件所有者为 root"
  fi

  if echo "$COMMAND" | grep -qE 'kill\s+-9\s+1\b|killall|pkill\s+-9'; then
    ask "检测到批量杀进程操作，请确认"
  fi
  if echo "$COMMAND" | grep -qE 'shutdown|reboot|halt|poweroff'; then
    deny "拦截: 系统关机/重启操作"
  fi

  if echo "$COMMAND" | grep -qE '(env|printenv|set)\s*\|.*curl|curl.*\$\(env'; then
    deny "拦截: 疑似将环境变量发送至外部"
  fi

  if echo "$COMMAND" | grep -qE 'mkfs\.|diskutil\s+eraseDisk|dd\s+if=.*of=/dev/'; then
    deny "拦截: 磁盘格式化/覆写操作"
  fi

  allow "Bash 命令通过黑名单检查"
fi

if [ "$TOOL_NAME" = "Write" ] || [ "$TOOL_NAME" = "Edit" ]; then
  if echo "$FILE_PATH" | grep -qE '^(/etc/|/System/|/usr/|/var/|/Library/)'; then
    deny "拦截: 修改系统关键路径 $FILE_PATH"
  fi

  if echo "$FILE_PATH" | grep -qE '\.ssh/(authorized_keys|config|id_|known_hosts)|\.gnupg/'; then
    ask "正在修改 SSH/GPG 敏感文件，请确认"
  fi

  if [ "$TOOL_NAME" = "Write" ] && [ -n "$CONTENT" ]; then
    if echo "$CONTENT" | grep -qE '(AKIA[0-9A-Z]{16}|sk-[a-zA-Z0-9]{32,}|BEGIN (RSA|EC|OPENSSH) PRIVATE KEY)'; then
      deny "拦截: 写入内容疑似包含密钥/凭证"
    fi
  fi

  allow "文件操作通过黑名单检查"
fi

allow "默认放行: $TOOL_NAME"
