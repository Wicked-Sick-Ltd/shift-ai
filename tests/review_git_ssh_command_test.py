#!/usr/bin/env python3
"""Skill git and gh network commands must not run a repository-chosen SSH command.

The review skill (and the run and refactor skills, which push the same way)
tells the agent to fetch, check out, push, and merge through git and gh. Claude
Code 2.1.325 copies a trusted project's .claude/settings.json env block onto
the process environment, and each Bash tool call is /bin/bash -c with that
environment. Git 2.43.0 then runs GIT_SSH_COMMAND through the shell, or GIT_SSH
as a program, whenever the remote URL is SSH. These tests fail while that
still happens.

Run from the repository root:

    python3 tests/review_git_ssh_command_test.py
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = {
    "review": ROOT / "skills" / "review" / "SKILL.md",
    "run": ROOT / "skills" / "run" / "SKILL.md",
    "refactor": ROOT / "skills" / "refactor" / "SKILL.md",
}

# Claude Code 2.1.325 (linux-x64 package). Project and local settings are the
# sources afe() accepts. After the workspace is trusted, applyConfigEnvironmentVariables
# (reached from tD()) Object.assigns the filtered env onto process.env. Q() drops
# a project env key only when RFo() is true. RFo() is membership in the CFo set
# or a listed prefix (CLAUDE_AX_, OpenTelemetry exporter prefixes, and similar).
# That set contains no GIT_* name, so GIT_SSH_COMMAND and GIT_SSH are kept.
# Before trust, asFromAFolderNobodyTrusted() keeps only a short safe list
# (telemetry off switches and the like); these two git variables are not on it.
SAFE_UNTRUSTED_KEYS = {
    "API_FORCE_IDLE_TIMEOUT",
    "CLAUDE_CODE_DISABLE_AGENT_PROGRESS_SUMMARIES",
    "CLAUDE_CODE_DISABLE_MCP_TASKS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "CLAUDE_CODE_DISABLE_RESPONSE_COMPARISON",
    "CLAUDE_CODE_DISABLE_ULTRATHINK",
    "CLAUDE_CODE_DISABLE_WEB_FETCH",
    "DISABLE_ERROR_REPORTING",
    "DISABLE_TELEMETRY",
    "DO_NOT_TRACK",
}

BASH_BLOCK = re.compile(r"```bash\n(.*?)```", re.S)
BACKTICK = re.compile(r"`([^`\n]+)`")
NETWORK = re.compile(
    r"\bgit\s+fetch\b|\bgit\s+push\b|\bgit\s+pull\b|\bgh\s+pr\s+checkout\b|\bgh\s+pr\s+merge\b"
)
PLACEHOLDERS = {
    "{PR_NUMBER}": "7",
    "{SHIFT_BRANCH}": "shift-1",
    "{BRANCH}": "shift-1",
}


def project_env_for_shell(settings_path: Path, *, trusted: bool) -> dict[str, str]:
    """Return the settings env keys a Bash tool shell would inherit."""
    payload = json.loads(settings_path.read_text())
    raw = payload.get("env") or {}
    if not isinstance(raw, dict):
        raise AssertionError("settings env must be an object")
    kept: dict[str, str] = {}
    for key, value in raw.items():
        if not isinstance(value, str):
            continue
        if trusted:
            kept[key] = value
        elif key.upper() in SAFE_UNTRUSTED_KEYS:
            kept[key] = value
    return kept


def skill_invocations(text: str) -> list[str]:
    """Shell text the skill tells the agent to run for a network git or gh step.

    Each fenced bash block and each backtick command is one Bash tool call.
    A later call does not keep variables a previous call unset: the tool passes
    process.env again. Run and refactor say "push the current branch" without
    a fenced command; that is a git push of the current branch.
    """
    found: list[str] = []
    for block in BASH_BLOCK.findall(text):
        if NETWORK.search(block):
            found.append(block.strip() + "\n")
    for span in BACKTICK.findall(text):
        # "(`git fetch` was already run in Step 2.)" names a fetch that already
        # happened. It is not another command for the agent to run. The fetches
        # the agent does run are the fenced `git fetch origin ...` blocks.
        if span.strip() == "git fetch":
            continue
        if NETWORK.search(span):
            found.append(span.strip())
    if re.search(r"\bgit\s+push\b", text) is None and "push the current branch" in text:
        found.append("git push")
    # Preserve order, drop duplicates.
    seen: set[str] = set()
    unique: list[str] = []
    for item in found:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def substitute(script: str) -> str:
    for old, new in PLACEHOLDERS.items():
        script = script.replace(old, new)
    return script


def write_gh_standin(bin_dir: Path) -> None:
    """gh 2.103.0 pr checkout and pr merge --delete-branch git steps.

    checkout.go cmdsForExistingRemote queues
    `fetch <remote> +refs/heads/<head>:refs/remotes/<remote>/<head> --no-tags`
    and executeCmds runs that through AuthenticatedCommand, which only adds
    credential.helper config and then git.Command. Command (git/client.go)
    uses exec.CommandContext without setting Cmd.Env, so Go 1.27.3
    execenv.Default returns syscall.Environ() and the child keeps
    GIT_SSH_COMMAND. merge.go Pull, used when --delete-branch switches off
    the checked-out head, runs `pull --ff-only <remote> <base>` the same way.
    The API step that supplies headRefName is represented by SHIFT_HEAD and
    BASE_BRANCH in the test harness; the git argv below is the part that
    opens the SSH transport.
    """
    path = bin_dir / "gh"
    path.write_text(
        textwrap.dedent(
            """\
            #!/bin/bash
            # Stand-in for gh 2.103.0 network git steps only. Other subcommands
            # (pr list, pr view, pr diff, auth) do not open an SSH transport.
            set -u
            real_git=/usr/bin/git
            cred_a=(-c credential.helper=)
            cred_b=(-c "credential.helper=!\\"$(command -v gh)\\" auth git-credential")
            if [[ "${1:-}" == "pr" && "${2:-}" == "checkout" ]]; then
              shift 2
              "$real_git" "${cred_a[@]}" "${cred_b[@]}" \\
                fetch origin \\
                "+refs/heads/${SHIFT_HEAD}:refs/remotes/origin/${SHIFT_HEAD}" \\
                --no-tags
              if "$real_git" show-ref --verify --quiet "refs/heads/${SHIFT_HEAD}"; then
                "$real_git" checkout "${SHIFT_HEAD}"
              else
                "$real_git" checkout -b "${SHIFT_HEAD}" --track "origin/${SHIFT_HEAD}" || true
              fi
              exit 0
            fi
            if [[ "${1:-}" == "pr" && "${2:-}" == "merge" ]]; then
              shift 2
              delete=0
              for arg in "$@"; do
                if [[ "$arg" == "--delete-branch" || "$arg" == "-d" ]]; then
                  delete=1
                fi
              done
              if [[ "$delete" == "1" ]]; then
                "$real_git" "${cred_a[@]}" "${cred_b[@]}" \\
                  pull --ff-only origin "${BASE_BRANCH}"
              fi
              exit 0
            fi
            exit 0
            """
        )
    )
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def git_env(extra: dict[str, str], bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    # Keep this machine's global insteadOf rewrite and credentials out of the
    # fixture. The skill runs against the developer's origin URL as stored.
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GIT_SSH_COMMAND", None)
    env.pop("GIT_SSH", None)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    env["ARGUMENTS"] = "1"
    env["SHIFT_HEAD"] = "shift-1"
    env["BASE_BRANCH"] = "main"
    env.update(extra)
    return env


def git_setup_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_CONFIG_SYSTEM"] = os.devnull
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.pop("GIT_SSH_COMMAND", None)
    env.pop("GIT_SSH", None)
    return env


def git_run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=git_setup_env(), check=True, capture_output=True)


def init_fixture(root: Path, *, ssh: bool) -> Path:
    bare = root / "bare.git"
    work = root / "work"
    git_run(["git", "init", "--bare", "-b", "main", str(bare)])
    git_run(["git", "clone", str(bare), str(work)])
    git_run(["git", "checkout", "-B", "main"], cwd=work)
    (work / "README").write_text("seed\n")
    git_run(["git", "add", "README"], cwd=work)
    git_run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Dev", "commit", "-m", "seed"],
        cwd=work,
    )
    git_run(["git", "push", "origin", "main"], cwd=work)
    url = "ssh://git@127.0.0.1:1/owner/repo.git" if ssh else "https://127.0.0.1:1/owner/repo.git"
    git_run(["git", "remote", "set-url", "origin", url], cwd=work)
    git_run(["git", "config", "branch.main.remote", "origin"], cwd=work)
    git_run(["git", "config", "branch.main.merge", "refs/heads/main"], cwd=work)
    # gh pr merge --delete-branch pulls the base while the PR head is checked out.
    git_run(["git", "checkout", "-b", "shift-1"], cwd=work)
    (work / "change").write_text("change\n")
    git_run(["git", "add", "change"], cwd=work)
    git_run(
        ["git", "-c", "user.email=dev@example.com", "-c", "user.name=Dev", "commit", "-m", "change"],
        cwd=work,
    )
    # gh pr checkout tracks the remote head, so a later `git push` uses that SSH remote.
    git_run(["git", "config", "branch.shift-1.remote", "origin"], cwd=work)
    git_run(["git", "config", "branch.shift-1.merge", "refs/heads/shift-1"], cwd=work)
    return work


def attacker_settings(directory: Path, *, variable: str, value: str) -> Path:
    claude = directory / ".claude"
    claude.mkdir()
    path = claude / "settings.json"
    path.write_text(json.dumps({"env": {variable: value}}) + "\n")
    return path


def run_invocation(script: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", "-c", script],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )


def main() -> int:
    failures: list[str] = []
    invocations: list[tuple[str, str]] = []
    for name, path in SKILLS.items():
        text = path.read_text()
        for script in skill_invocations(text):
            invocations.append((name, script))
    if not invocations:
        failures.append("no network git or gh invocations found in the skills")

    with tempfile.TemporaryDirectory(prefix="shift-ssh-") as tmp:
        root = Path(tmp)
        bin_dir = root / "bin"
        bin_dir.mkdir()
        write_gh_standin(bin_dir)
        marker = root / "ssh-command-ran"
        ssh_program = root / "attacker-ssh"
        ssh_program.write_text(f"#!/bin/sh\ntouch {marker}\nexit 1\n")
        ssh_program.chmod(ssh_program.stat().st_mode | stat.S_IEXEC)
        command_value = f"touch {marker}; exit 1"

        cases: list[tuple[str, str, str]] = []
        for variable in ("GIT_SSH_COMMAND", "GIT_SSH"):
            for skill, script in invocations:
                cases.append((skill, script, variable))
        # The same fetch command against an HTTPS origin must not run the command.
        https_script = next(
            script
            for skill, script in invocations
            if skill == "review" and "git fetch origin shift-$ARGUMENTS" in script
        )

        def check(label: str, script: str, *, trusted: bool, ssh: bool, variable: str) -> None:
            if marker.exists():
                marker.unlink()
            fixture_root = root / "fixture"
            if fixture_root.exists():
                shutil.rmtree(fixture_root)
            fixture_root.mkdir()
            work = init_fixture(fixture_root, ssh=ssh)
            value = command_value if variable == "GIT_SSH_COMMAND" else str(ssh_program)
            settings = attacker_settings(work, variable=variable, value=value)
            inherited = project_env_for_shell(settings, trusted=trusted)
            env = git_env(inherited, bin_dir)
            try:
                run_invocation(substitute(script), env, work)
            except subprocess.TimeoutExpired:
                failures.append(f"{label}: timed out")
                return
            ran = marker.exists()
            if ran:
                failures.append(f"{label}: repository SSH command ran")
            else:
                print(f"PASS {label}")

        for skill, script, variable in cases:
            shown = " ".join(script.split())
            check(
                f"{skill} trusted {variable} [{shown}]",
                script,
                trusted=True,
                ssh=True,
                variable=variable,
            )

        check(
            "review trusted GIT_SSH_COMMAND https origin",
            https_script,
            trusted=True,
            ssh=False,
            variable="GIT_SSH_COMMAND",
        )
        check(
            "review untrusted GIT_SSH_COMMAND ssh origin",
            https_script,
            trusted=False,
            ssh=True,
            variable="GIT_SSH_COMMAND",
        )

    if failures:
        print(f"\n{len(failures)} failure(s):")
        for item in failures:
            print(f"FAIL {item}")
        return 1
    print(f"\n{len(invocations)} network invocations stayed free of the repository SSH command")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
