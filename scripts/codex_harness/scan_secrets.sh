#!/usr/bin/env bash
set -euo pipefail

PATTERNS=(
  'AKIA[0-9A-Z]{16}'
  'sk-[A-Za-z0-9]{32,}'
  'gh[pous]_[A-Za-z0-9]{36,}'
  'xox[baprs]-[A-Za-z0-9-]+'
  'AIza[0-9A-Za-z_-]{35}'
  'ya29\.[0-9A-Za-z_-]+'
  'BEGIN ([A-Z0-9 ]+ )?PRIVATE KEY'
)

STAGED=$(git diff --cached --name-only --diff-filter=d 2>/dev/null || true)
if [ -z "$STAGED" ]; then
  exit 0
fi

FOUND=0

while IFS= read -r file; do
  if [ -z "$file" ] || [ ! -e "$file" ]; then
    continue
  fi

  if file "$file" | grep -qi "binary"; then
    continue
  fi

  if printf '%s\n' "$file" | grep -qE '(^|/)(tests?|spec)/|(^|/)(test_|.*_test\.|spec_|.*\.test\.)'; then
    continue
  fi

  CONTENT=$(git show :"$file" 2>/dev/null || true)

  for pattern in "${PATTERNS[@]}"; do
    if printf '%s' "$CONTENT" | grep -qE "$pattern"; then
      echo "[secrets-scan] $file matches pattern: $pattern"
      FOUND=1
    fi
  done
done <<< "$STAGED"

if [ "$FOUND" -ne 0 ]; then
  echo "[secrets-scan] Commit blocked. Move secrets to environment variables and retry."
  exit 1
fi
