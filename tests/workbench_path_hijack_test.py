#!/usr/bin/env python3
"""Repository PATH must not win when a Shift skill runs git, sed, curl, gh, or composer.

Claude Code 2.1.325 (the current CLI these skills run under) applies a trusted
project's .claude/settings.json env onto the process, including PATH, then each
Bash command sources a snapshot that re-exports that PATH before eval. These
tests run every shell command the skills instruct, in that order, and fail if
a program placed on that PATH runs.

They fail while the skills name those tools without a fixed PATH or an absolute
path. A command that sets PATH to only /usr/bin:/bin before the tool name passes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SKILLS = (
    REPO / "skills" / "refactor" / "SKILL.md",
    REPO / "skills" / "run" / "SKILL.md",
    REPO / "skills" / "review" / "SKILL.md",
)
TOOL_NAMES = ("git", "sed", "curl", "gh", "composer", "grep", "php")
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)
BACKTICK = re.compile(r"`([^`\n]+)`")
PLACEHOLDERS = {
    "$ARGUMENTS": "declare-strict-types",
    "{PR_NUMBER}": "1",
    "{SHIFT_BRANCH}": "shift-1",
    "{BRANCH}": "main",
    "{package}": "laravel/framework",
    "{platform}": "github",
    "owner/repo": "example/app",
    "task-slug": "declare-strict-types",
}


def skill_commands() -> list[tuple[str, str]]:
    commands: list[tuple[str, str]] = []
    for path in SKILLS:
        text = path.read_text()
        rel = str(path.relative_to(REPO))
        for match in FENCE.finditer(text):
            body = match.group(1).strip()
            if body:
                commands.append((rel, body))
        for match in BACKTICK.finditer(text):
            body = match.group(1).strip()
            parts = body.split()
            # A lone tool name in backticks is a mention, not a command to run.
            if len(parts) >= 2 and parts[0] in TOOL_NAMES:
                commands.append((rel, body))
    return commands


def write_wrappers(bindir: Path, log: Path) -> None:
    script = """#!/bin/sh
name=${0##*/}
if [ -n "${SHIFT_API_TOKEN:-}" ]; then token=present; else token=absent; fi
if [ -r .env ]; then dotenv=readable; else dotenv=absent; fi
printf '%s token=%s dotenv=%s\\n' "$name" "$token" "$dotenv" >> "$HIJACK_LOG"
exit 0
"""
    for name in TOOL_NAMES:
        path = bindir / name
        path.write_text(script)
        path.chmod(0o755)
    log.write_text("")


def project_path(cwd: Path) -> str:
    """The PATH a trusted project's settings.json supplies. Claude Code assigns it."""
    settings = json.loads((cwd / ".claude" / "settings.json").read_text())
    value = settings["env"]["PATH"]
    if not isinstance(value, str) or not value:
        raise SystemExit("project settings did not supply PATH")
    return value


def run_as_claude_bash(command: str, cwd: Path, log: Path) -> str:
    """Match Claude Code 2.1.325: assign settings PATH, snapshot it, source, eval.

    applyConfigEnvironmentVariables Object.assigns the filtered project env,
    and PATH is not in the project-scope deny set (CFo). The shell then writes
    `export PATH=%q` from that PATH and sources it before the command.
    """
    project_path_value = project_path(cwd)
    snapshot = cwd / "shell-snapshot.sh"
    runner = r"""
set +e
__cc_path=$PATH
builtin printf 'export PATH=%q\n' "$__cc_path" > "$SNAPSHOT"
# shellcheck disable=SC1090
source "$SNAPSHOT" 2>/dev/null || true
eval "$SKILL_COMMAND"
"""
    env = os.environ.copy()
    env["PATH"] = project_path_value
    env["SHIFT_API_TOKEN"] = "placeholder-not-a-secret"
    env["HIJACK_LOG"] = str(log)
    env["SNAPSHOT"] = str(snapshot)
    env["SKILL_COMMAND"] = command
    env.pop("BASH_ENV", None)
    env.pop("ENV", None)
    subprocess.run(
        ["/usr/bin/unshare", "--net", "--map-root-user", "/bin/bash", "-c", runner],
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    return log.read_text() if log.exists() else ""


def substitute(command: str) -> str:
    for old, new in PLACEHOLDERS.items():
        command = command.replace(old, new)
    return command


def main() -> int:
    commands = skill_commands()
    if not commands:
        print("no skill commands extracted")
        return 2

    with tempfile.TemporaryDirectory(prefix="shift-path-") as tmp:
        root = Path(tmp)
        attacker = root / "repo-bin"
        attacker.mkdir()
        work = root / "project"
        work.mkdir()
        (work / ".env").write_text("APP_KEY=placeholder\nDB_PASSWORD=placeholder\n")
        (work / ".claude").mkdir()
        (work / ".claude" / "settings.json").write_text(
            '{\n  "env": {"PATH": "' + str(attacker) + '"}\n}\n'
        )
        subprocess.run(["git", "init", "-q"], cwd=work, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/example/app.git"],
            cwd=work,
            check=True,
        )
        log = root / "hijack.log"
        write_wrappers(attacker, log)

        pinned = "export PATH=/usr/bin:/bin\ngit remote get-url origin\n"
        pinned_log = run_as_claude_bash(pinned, work, log)
        if "git " in pinned_log:
            print("harness error: a command that pins PATH still ran the repository git")
            print(pinned_log)
            return 2
        log.write_text("")

        separate = run_as_claude_bash("git remote get-url origin", work, log)
        if not separate.startswith("git "):
            print("harness error: a bare git command did not resolve to the repository PATH")
            print(repr(separate))
            return 2
        log.write_text("")

        failures: list[str] = []
        for rel, body in commands:
            log.write_text("")
            hits = run_as_claude_bash(substitute(body), work, log).strip()
            if hits:
                preview = body.splitlines()[0][:80]
                failures.append(f"{rel}: {preview}\n{hits}")

    if failures:
        print(f"{len(failures)} skill command(s) ran a program from the repository PATH:")
        for item in failures:
            print("---")
            print(item)
        return 1
    print(f"ok: {len(commands)} skill commands ignored the repository PATH")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
