#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
TARGET_DIR="$HOME/.codex"
GLOBAL_BACKUP_DIR="$TARGET_DIR/backups/harness-$(date +%Y%m%d-%H%M%S)"
REPO_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
REPO_CONFIG_TARGET="$REPO_ROOT/.codex/config.toml"

mkdir -p "$TARGET_DIR" "$TARGET_DIR/hooks" "$TARGET_DIR/rules" "$GLOBAL_BACKUP_DIR"

backup_file() {
  local path="$1"
  local backup_dir="$2"
  local name="$3"
  if [ -f "$path" ]; then
    mkdir -p "$backup_dir"
    cp "$path" "$backup_dir/$name"
  fi
}

backup_file "$TARGET_DIR/config.toml" "$GLOBAL_BACKUP_DIR" "config.toml"
backup_file "$TARGET_DIR/AGENTS.md" "$GLOBAL_BACKUP_DIR" "AGENTS.md"
backup_file "$TARGET_DIR/hooks.json" "$GLOBAL_BACKUP_DIR" "hooks.json"
backup_file "$TARGET_DIR/rules/default.rules" "$GLOBAL_BACKUP_DIR" "default.rules"
backup_file "$TARGET_DIR/hooks/pre_tool_use_guard.py" "$GLOBAL_BACKUP_DIR" "pre_tool_use_guard.py"
backup_file "$TARGET_DIR/hooks/scan_secrets.sh" "$GLOBAL_BACKUP_DIR" "scan_secrets.sh"

cp "$SCRIPT_DIR/config.toml" "$TARGET_DIR/config.toml"
cp "$SCRIPT_DIR/AGENTS.md" "$TARGET_DIR/AGENTS.md"
cp "$SCRIPT_DIR/hooks.json" "$TARGET_DIR/hooks.json"
cp "$SCRIPT_DIR/default.rules" "$TARGET_DIR/rules/default.rules"
cp "$SCRIPT_DIR/pre_tool_use_guard.py" "$TARGET_DIR/hooks/pre_tool_use_guard.py"
cp "$SCRIPT_DIR/scan_secrets.sh" "$TARGET_DIR/hooks/scan_secrets.sh"

chmod +x "$TARGET_DIR/hooks/pre_tool_use_guard.py" "$TARGET_DIR/hooks/scan_secrets.sh"

mkdir -p "$(dirname "$REPO_CONFIG_TARGET")"
REPO_BACKUP_DIR="$REPO_ROOT/.codex/backups/harness-$(date +%Y%m%d-%H%M%S)"
backup_file "$REPO_CONFIG_TARGET" "$REPO_BACKUP_DIR" "config.toml"
cp "$SCRIPT_DIR/tradingcat.repo.config.toml" "$REPO_CONFIG_TARGET"

echo "Installed Codex harness assets to $TARGET_DIR"
echo "Backed up previous global files to $GLOBAL_BACKUP_DIR"
echo "Updated TradingCat repo config at $REPO_CONFIG_TARGET"
if [ -d "$REPO_BACKUP_DIR" ]; then
  echo "Backed up previous repo config to $REPO_BACKUP_DIR"
fi
echo "Restart Codex to pick up the new global config, rules, hooks, and AGENTS defaults."
