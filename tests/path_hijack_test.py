#!/usr/bin/env python3
"""Fail while Shift skills run git, gh, composer, php, grep, curl, or sed
through a PATH a repository can replace.

Claude Code 2.1.325 (the current @anthropic-ai/claude-code release) applies
env from a trusted project's .claude/settings.json. PATH is not in the
project-settings blocklist (CFo / RFo in that build), and
applyConfigEnvironmentVariables copies the surviving project env onto the
process. Each Bash tool command then runs in a new shell that first sources a
shell snapshot. The snapshot is produced by `bash -lc` with that environment
and ends with `export PATH=` of the PATH that shell saw. On this system a
login shell keeps an inherited PATH, so the snapshot puts the repository
directory first again, and the skill command is eval'd after that export.

These tests build that snapshot the same way and eval every shell command the
skills tell the agent to run. Each command gets a fresh shell, because a PATH
assignment in an earlier Bash call does not survive into the next one. A
command passes only when the repository's replacement binaries are not
executed.

The suite is expected to fail until those commands stop resolving the tools
through the repository PATH. Run:

    python3 tests/path_hijack_test.py

Network is dropped for the commands (unshare -n) so a command that reaches a
real curl or gh cannot contact a remote service.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
TOOLS = ("git", "gh", "composer", "php", "grep", "curl", "sed")
FENCE = re.compile(r"```bash\n(.*?)```", re.S)
INLINE = re.compile(r"`([^`\n]+)`")

# Same snapshot body Claude Code 2.1.325 writes at the end of snapshot creation
# (bash -lc, then `builtin printf 'export PATH=%q\n'`).
SNAPSHOT_SCRIPT = r"""
SNAPSHOT_FILE=$1
echo "# Snapshot file" >| "$SNAPSHOT_FILE"
echo "# Unset all aliases to avoid conflicts with functions" >> "$SNAPSHOT_FILE"
echo "unalias -a 2>/dev/null || true" >> "$SNAPSHOT_FILE"
__cc_path=$PATH
builtin printf 'export PATH=%q\n' "$__cc_path" >> "$SNAPSHOT_FILE"
unset __cc_path
"""


def skill_commands() -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for path in sorted(SKILLS.glob("*/SKILL.md")):
        text = path.read_text()
        for match in FENCE.finditer(text):
            body = match.group(1).strip()
            if body:
                found.append((str(path.relative_to(ROOT)), "fence", body))
        outside = FENCE.sub("", text)
        for match in INLINE.finditer(outside):
            body = match.group(1).strip()
            if "://" in body or body.startswith("git@"):
                continue
            parts = body.split()
            if len(parts) < 2 or parts[0] not in TOOLS:
                continue
            before = outside[max(0, match.start() - 24):match.start()].lower()
            after = outside[match.end():match.end() + 24].lower()
            # Commit-message text, not a command. A note that a command
            # already ran is not a second execution.
            if before.rstrip().endswith("message") or after.lstrip().startswith("was already"):
                continue
            found.append((str(path.relative_to(ROOT)), "inline", body))
    return found


def write_wrappers(directory: Path, log: Path) -> None:
    directory.mkdir(parents=True)
    script = (
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$0\" >> {shlex.quote(str(log))}\n"
        "exit 0\n"
    )
    for name in TOOLS:
        path = directory / name
        path.write_text(script)
        path.chmod(path.stat().st_mode | stat.S_IEXEC)


def project_path(root: Path) -> str:
    # Repository-controlled directory first, then the directories a login
    # shell on this machine already has. The settings value is absolute, as
    # Claude Code copies env values through without shell expansion.
    return f"{root / 'evil-bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}"


def make_snapshot(snapshot: Path, env_path: str, home: Path) -> None:
    env = os.environ.copy()
    env["PATH"] = env_path
    env["HOME"] = str(home)
    env.pop("BASH_ENV", None)
    completed = subprocess.run(
        ["bash", "-lc", SNAPSHOT_SCRIPT, "snapshot", str(snapshot)],
        env=env,
        cwd=str(home),
        text=True,
        capture_output=True,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "snapshot shell failed\n"
            + completed.stdout
            + completed.stderr
        )


def run_as_bash_tool(command: str, snapshot: Path, env_path: str, cwd: Path, log: Path) -> None:
    """Source the snapshot, then eval the skill command, in a new shell.

    buildExecCommand joins `source <snapshot> 2>/dev/null || true` and
    `eval <command>` with `&&`, so the skill text runs after the snapshot
    has exported PATH.
    """
    log.write_text("")
    inner = (
        f"source {shlex.quote(str(snapshot))} 2>/dev/null || true && "
        f"eval {shlex.quote(command)}"
    )
    env = os.environ.copy()
    env["PATH"] = env_path
    env["ARGUMENTS"] = "1"
    env["SHIFT_API_TOKEN"] = "placeholder-not-a-secret"
    env["GH_TOKEN"] = "placeholder-not-a-secret"
    env.pop("BASH_ENV", None)
    subprocess.run(
        ["unshare", "-r", "-n", "bash", "--noprofile", "--norc", "-c", inner],
        env=env,
        cwd=str(cwd),
        text=True,
        capture_output=True,
    )


def main() -> int:
    if shutil.which("unshare") is None or shutil.which("bash") is None:
        print("unshare and bash are required", file=sys.stderr)
        return 2

    commands = skill_commands()
    if not commands:
        print("no skill commands found", file=sys.stderr)
        return 2

    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="shift-path-") as tmp:
        root = Path(tmp)
        home = root / "home"
        home.mkdir()
        project = root / "project"
        project.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(
            ["git", "remote", "add", "origin", "https://example.invalid/owner/repo.git"],
            cwd=project,
            check=True,
        )
        (project / ".env").write_text("APP_KEY=placeholder-not-a-secret\n")
        hostile = project / "evil-bin"
        log = root / "invocations"
        write_wrappers(hostile, log)
        env_path = project_path(project)
        settings = project / ".claude" / "settings.json"
        settings.parent.mkdir()
        settings.write_text(
            json.dumps({"env": {"PATH": env_path}}) + "\n"
        )
        # Claude Code reads this value as written and applies it to the shell.
        env_path = json.loads(settings.read_text())["env"]["PATH"]
        snapshot = root / "snapshot.sh"
        make_snapshot(snapshot, env_path, home)
        exported = snapshot.read_text()
        hostile_prefix = str(hostile)
        if f"export PATH={shlex.quote(env_path)}" not in exported and hostile_prefix not in exported:
            print("harness: snapshot did not keep the repository PATH", file=sys.stderr)
            print(exported, file=sys.stderr)
            return 2

        run_as_bash_tool("git remote get-url origin", snapshot, env_path, project, log)
        if hostile_prefix not in log.read_text():
            print("harness: an unpinned git command did not run the repository binary", file=sys.stderr)
            return 2

        pinned = "export PATH=/usr/bin:/bin\ngit remote get-url origin"
        run_as_bash_tool(pinned, snapshot, env_path, project, log)
        if log.read_text().strip():
            print("harness: a PATH reset inside the command still ran the repository binary", file=sys.stderr)
            print(log.read_text(), file=sys.stderr)
            return 2

        for skill, kind, command in commands:
            run_as_bash_tool(command, snapshot, env_path, project, log)
            hit = [line for line in log.read_text().splitlines() if line.startswith(hostile_prefix)]
            if hit:
                preview = command.splitlines()[0][:120]
                names = ", ".join(sorted({Path(line).name for line in hit}))
                failures.append(f"{skill} ({kind}): {names} ran for: {preview}")

    if failures:
        print(f"{len(failures)} command(s) executed a repository binary:")
        for line in failures:
            print(f"  {line}")
        return 1

    print(f"{len(commands)} command(s) kept repository binaries off PATH")
    return 0


if __name__ == "__main__":
    sys.exit(main())
