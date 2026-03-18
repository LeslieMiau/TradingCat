#!/usr/bin/env bash

reports_root() {
  local root_dir
  root_dir="${TRADINGCAT_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
  printf '%s/data/reports\n' "$root_dir"
}

ensure_report_dir() {
  local base_dir timestamp report_dir
  base_dir="${1:-$(reports_root)}"
  timestamp="$(date '+%Y%m%d-%H%M%S')"
  report_dir="$base_dir/$timestamp"
  mkdir -p "$report_dir"
  printf '%s\n' "$report_dir"
}

latest_report_dir() {
  local base_dir
  base_dir="${1:-$(reports_root)}"
  if [[ ! -d "$base_dir" ]]; then
    return 1
  fi
  find "$base_dir" -mindepth 1 -maxdepth 1 -type d | sort | tail -n 1
}

resolve_report_dir() {
  local ref base_dir
  ref="$1"
  base_dir="${2:-$(reports_root)}"
  if [[ -d "$ref" ]]; then
    printf '%s\n' "$ref"
    return 0
  fi
  if [[ -d "$base_dir/$ref" ]]; then
    printf '%s\n' "$base_dir/$ref"
    return 0
  fi
  return 1
}
