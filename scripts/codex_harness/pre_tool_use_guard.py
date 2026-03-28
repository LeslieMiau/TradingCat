#!/usr/bin/env python3

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Optional


FORCE_PUSH_FLAGS = {"-f", "--force", "--force-with-lease"}
DANGEROUS_RM_TARGETS = {
    "/",
    "~",
    "$HOME",
    "..",
    "../",
    "*",
    "./*",
    "../*",
    "~/*",
}


def load_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )
    sys.exit(0)


def tokenize(command: str) -> list[str]:
    try:
        return shlex.split(command)
    except ValueError:
        return []


def strip_sudo(tokens: list[str]) -> list[str]:
    if tokens and tokens[0] == "sudo":
        return tokens[1:]
    return tokens


def is_force_push(tokens: list[str]) -> bool:
    if len(tokens) < 2 or tokens[0] != "git" or tokens[1] != "push":
        return False
    return any(flag in FORCE_PUSH_FLAGS for flag in tokens[2:])


def is_remote_pipe(command: str) -> bool:
    return bool(re.search(r"\b(?:curl|wget)\b.*\|\s*(?:bash|sh|zsh)\b", command))


def dangerous_rm_target(tokens: list[str]) -> Optional[str]:
    if not tokens or tokens[0] != "rm":
        return None
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        if token in DANGEROUS_RM_TARGETS:
            return token
        if token.startswith("/") and token.endswith("/*"):
            return token
        if token.endswith("/..") or token == ".":
            return token
    return None


def run_secrets_scan(cwd: str) -> tuple[bool, str]:
    script = Path(__file__).with_name("scan_secrets.sh")
    result = subprocess.run(
        ["/bin/bash", str(script)],
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, ""
    output = (result.stdout or result.stderr).strip()
    return False, output


def main() -> None:
    payload = load_payload()
    if payload.get("tool_name") != "Bash":
        return

    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return

    tokens = strip_sudo(tokenize(command))
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        cwd = os.getcwd()

    if is_remote_pipe(command):
        deny("Remote scripts piped into a shell are blocked.")

    if is_force_push(tokens):
        deny("Forced git push is blocked.")

    rm_target = dangerous_rm_target(tokens)
    if rm_target is not None:
        deny(f"Broad rm target is blocked: {rm_target}")

    if len(tokens) >= 2 and tokens[0] == "git" and tokens[1] == "commit":
        ok, output = run_secrets_scan(cwd)
        if not ok:
            reason = "Secrets scan blocked git commit."
            if output:
                reason = f"{reason} {output.splitlines()[0]}"
            deny(reason)


if __name__ == "__main__":
    main()
