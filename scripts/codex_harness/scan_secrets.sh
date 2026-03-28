#!/usr/bin/env bash
# Scan staged files for sensitive information before git commit
set -euo pipefail

PATTERNS=(
  'AKIA[0-9A-Z]{16}'
  'sk-[a-zA-Z0-9]{32,}'
  'ghp_[a-zA-Z0-9]{36}'
  'gho_[a-zA-Z0-9]{36}'
  'ghs_[a-zA-Z0-9]{36}'
  'xox[baprs]-[a-zA-Z0-9\-]+'
  'AIza[0-9A-Za-z\-_]{35}'
  'ya29\.[0-9A-Za-z\-_]+'
  'BEGIN (RSA|EC|OPENSSH) PRIVATE KEY'
  'password\s*=\s*["\047][^"\047]{4,}'
  'secret\s*=\s*["\047][^"\047]{4,}'
  'token\s*=\s*["\047][^"\047]{8,}'
  '[a-zA-Z0-9+/]{40,}={0,2}'
)

STAGED=$(git diff --cached --name-only --diff-filter=d 2>/dev/null || true)

if [ -z "$STAGED" ]; then
  exit 0
fi

FOUND=0

for pattern in "${PATTERNS[@]}"; do
  MATCHES=$(echo "$STAGED" | xargs git show :"{}" 2>/dev/null | grep -E "$pattern" || true)
  if [ -n "$MATCHES" ]; then
    FOUND=1
    echo "⚠️  [secrets-scan] Potential sensitive info detected (pattern: $pattern)"
  fi
done

while IFS= read -r file; do
  if file "$file" | grep -q "binary"; then
    continue
  fi

  CONTENT=$(git show :"$file" 2>/dev/null || true)

  for pattern in "${PATTERNS[@]}"; do
    if echo "$CONTENT" | grep -qE "$pattern"; then
      if echo "$file" | grep -qE "(test_|_test\.|spec_|\.test\.)"; then
        continue
      fi
      echo "⚠️  [secrets-scan] $file — matches pattern: $pattern"
      FOUND=1
    fi
  done
done <<< "$STAGED"

if [ "$FOUND" -eq 1 ]; then
  echo ""
  echo "❌ Commit blocked: sensitive information detected in staged files."
  echo "   Move secrets to environment variables, then retry."
  exit 1
fi

echo "✅ [secrets-scan] No sensitive information found."
exit 0
