#!/usr/bin/env python3
"""SSH transport commands in the Shift skills must not run a repository-chosen command.

Claude Code 2.1.325 copies `.claude/settings.json` `env` into the session after
the workspace is trusted (`applyConfigEnvironmentVariables`, projectSettings /
localSettings). `GIT_SSH_COMMAND` is not in the project-settings blocklist, and
the Bash tool leaves it in the child environment unless subprocess scrubbing is
explicitly enabled. Git 2.43.0 then runs that value through the shell for an
SSH remote (`get_ssh_command` in connect.c).

These tests follow the commands the skills actually tell the agent to run.
They fail while those commands still honor:

- `GIT_SSH_COMMAND` from the trusted project settings env
- `GIT_SSH` from that same env
- `core.sshCommand` from the repo's local git config
- `core.sshCommand` injected through `GIT_CONFIG_COUNT` / `GIT_CONFIG_KEY_*` /
  `GIT_CONFIG_VALUE_*` in that same env

A passing fix, in each procedure below, clears `GIT_SSH_COMMAND` and `GIT_SSH`
for the git process and forces `core.sshCommand` to the `ssh` executable on
`PATH` (`command -v ssh`). Command-line `git -c core.sshCommand=...` overrides
repo config and `GIT_CONFIG_*`, but it does not override `GIT_SSH_COMMAND` or
`GIT_SSH`; those variables have to be removed from the environment of the git
process. The test places a local git transport named `ssh` first on `PATH`.
Resolving `ssh` from `PATH` is what reaches that transport.

The commit-and-push sections of `skills/run/SKILL.md` and
`skills/refactor/SKILL.md` have no explicit `git push` command today. The test
then runs the procedure the prose names: `git add -A`, `git commit`, and
`git push`. When that section contains a fenced bash block that runs
`git push`, that block is the procedure. Inline ``git push`` / ``git fetch``
commands are always run as well.

`skills/review/SKILL.md` fetches over SSH while locating the Shift branch and
pushes with ``git push`` before merging. Both are covered. `gh pr checkout`
and `gh pr merge` are not: this suite does not run `gh`.

Run:

    python3 tests/ssh_transport_env_test.py

The tests fail on purpose until the skills stop handing repository-controlled
SSH commands to git.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
RUN_SKILL = REPO / "skills" / "run" / "SKILL.md"
REFACTOR_SKILL = REPO / "skills" / "refactor" / "SKILL.md"
REVIEW_SKILL = REPO / "skills" / "review" / "SKILL.md"

BASH_FENCE = re.compile(r"```bash\n(.*?)```", re.S)
INLINE_CMD = re.compile(r"`([^`\n]+)`")
TRANSPORT = re.compile(r"\bgit\s+(?:push|fetch|pull|ls-remote)\b")


def section(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    finish = text.index(end, begin + len(start))
    return text[begin:finish]


def transport_procedures(section_text: str, *, implicit_commit_and_push: bool) -> list[str]:
    """Shell scripts the skill tells the agent to execute for git transport."""
    scripts: list[str] = []
    for fence in BASH_FENCE.finditer(section_text):
        body = fence.group(1)
        if TRANSPORT.search(body):
            scripts.append(body)
    for inline in INLINE_CMD.finditer(section_text):
        command = inline.group(1).strip()
        if TRANSPORT.search(command):
            scripts.append(command)
    if implicit_commit_and_push and not any("git push" in script for script in scripts):
        scripts.append(
            textwrap.dedent(
                """\
                git add -A
                git commit -m "$COMMIT_MSG"
                git push
                """
            )
        )
    if not scripts:
        raise AssertionError("skill section no longer names a git transport command")
    return scripts


def run_commit_and_push_scripts() -> list[str]:
    text = RUN_SKILL.read_text()
    body = section(text, "4. Check for uncommitted changes", "5. If the current branch matches")
    return transport_procedures(body, implicit_commit_and_push=True)


def refactor_commit_and_push_scripts() -> list[str]:
    text = REFACTOR_SKILL.read_text()
    body = section(text, "5. Check for uncommitted changes", "6. Build the `scs` connection string")
    return transport_procedures(body, implicit_commit_and_push=True)


def review_fetch_scripts() -> list[str]:
    text = REVIEW_SKILL.read_text()
    body = section(text, "## Step 2: Find the PR and Fetch Details", "## Step 3: Check for Uncommitted Changes")
    return transport_procedures(body, implicit_commit_and_push=False)


def review_push_scripts() -> list[str]:
    text = REVIEW_SKILL.read_text()
    body = section(text, "If the user confirms they want to merge:", "5. Merge using the appropriate method")
    return transport_procedures(body, implicit_commit_and_push=False)


def apply_trusted_project_env(base: dict[str, str], settings: dict) -> dict[str, str]:
    """Apply a trusted project's settings env the way Claude Code 2.1.325 does.

    `asFromAFolderNobodyTrusted` withholds arbitrary project env until the
    folder is trusted. After trust, `applyConfigEnvironmentVariables` assigns
    projectSettings env that survives `withoutInvalidSettingsEnv` and `Q`.
    `Q` drops a key only when `RFo` is true. `RFo` is the fixed blocklist
    `CFo` plus a few prefixes; `GIT_SSH_COMMAND`, `GIT_SSH`, and `GIT_CONFIG_*`
    are not on it. Invalid names and values that contain NUL are dropped.
    """
    env = dict(base)
    block = settings.get("env", {})
    if not isinstance(block, dict):
        return env
    for key, value in block.items():
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        if not isinstance(value, str) or "\0" in value:
            continue
        env[key] = value
    return env


class SshTransportEnvTest(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="shift-ssh-"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.marker = self.root / "attacker-ran"
        self.bare = self.root / "bare.git"
        self.home = self.root / "home"
        self.home.mkdir()
        self.ssh = self.root / "ssh"
        self.attacker = self.root / "attacker.sh"
        self._write_ssh_stub()
        self._write_attacker()
        self.author = {
            "GIT_AUTHOR_NAME": "Dev",
            "GIT_AUTHOR_EMAIL": "dev@example.com",
            "GIT_COMMITTER_NAME": "Dev",
            "GIT_COMMITTER_EMAIL": "dev@example.com",
        }
        self._git(None, ["init", "--bare", "-q", "-b", "main", str(self.bare)], cwd=self.root)
        self.origin = f"git@git.example:{self.bare}"

    def _write_ssh_stub(self) -> None:
        # Local stand-in for the ssh binary on PATH. Git 2.43.0 execs
        # `git-receive-pack '<path>'` / `git-upload-pack '<path>'` as one
        # argument when core.sshCommand is this program (connect.c use_shell).
        self.ssh.write_text(
            "#!/usr/bin/env python3\n"
            "import os, shlex, sys\n"
            "args = sys.argv[1:]\n"
            "if args[:1] == ['-G']:\n"
            "    sys.exit(0)\n"
            "i = 0\n"
            "while i < len(args):\n"
            "    option = args[i]\n"
            "    if option in ('-o', '-p', '-P', '-i', '-b', '-c', '-F', '-J', '-L', '-R', '-W'):\n"
            "        i += 2\n"
            "        continue\n"
            "    if option.startswith('-'):\n"
            "        i += 1\n"
            "        continue\n"
            "    break\n"
            "rest = args[i:]\n"
            "if len(rest) < 2:\n"
            "    sys.stderr.write('ssh stub: %r\\n' % (args,))\n"
            "    sys.exit(1)\n"
            "parts = shlex.split(rest[1])\n"
            "os.execvp(parts[0], parts)\n"
        )
        self.ssh.chmod(0o755)

    def _write_attacker(self) -> None:
        self.attacker.write_text(
            "#!/bin/sh\n"
            f"echo ran >> '{self.marker}'\n"
            "exit 1\n"
        )
        self.attacker.chmod(0o755)

    def _base_env(self) -> dict[str, str]:
        return {
            "PATH": f"{self.root}{os.pathsep}{os.environ['PATH']}",
            "HOME": str(self.home),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "ARGUMENTS": "1",
            "COMMIT_MSG": "save work before shift",
            **self.author,
        }

    def _git(self, extra: dict[str, str] | None, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        env = self._base_env()
        if extra:
            env.update(extra)
        return subprocess.run(["git", *args], cwd=cwd, env=env, text=True, capture_output=True)

    def _check_git(self, extra: dict[str, str] | None, args: list[str], cwd: Path) -> None:
        result = self._git(extra, args, cwd)
        if result.returncode != 0:
            raise AssertionError(
                f"{args} failed ({result.returncode})\n{result.stdout}\n{result.stderr}"
            )

    def _init_work(self, name: str, origin: str | None = None, *, publish: bool = True) -> Path:
        work = self.root / name
        self._check_git(None, ["init", "-q", "-b", "main", str(work)], self.root)
        self._check_git(None, ["commit", "--allow-empty", "-qm", "base"], work)
        self._check_git(None, ["remote", "add", "origin", origin or self.origin], work)
        if publish:
            self._check_git(None, ["push", "-u", "origin", "HEAD:main"], work)
        return work

    def _settings_env(self, updates: dict[str, str]) -> dict[str, str]:
        settings = {"env": updates}
        # The product reads this object from .claude/settings.json. The test
        # writes it so the input is the file the attack names, then applies
        # the trusted-project filter above.
        settings_path = self.root / ".claude" / "settings.json"
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings))
        loaded = json.loads(settings_path.read_text())
        return apply_trusted_project_env(self._base_env(), loaded)

    def _run_scripts(self, scripts: list[str], cwd: Path, env: dict[str, str]) -> list[subprocess.CompletedProcess[str]]:
        results = []
        for script in scripts:
            results.append(
                subprocess.run(
                    ["bash", "-c", script],
                    cwd=cwd,
                    env=env,
                    text=True,
                    capture_output=True,
                )
            )
        return results

    def _assert_attacker_did_not_run(self) -> None:
        if self.marker.exists():
            self.fail(
                "repository-controlled SSH command ran during the skill's git transport: "
                + self.marker.read_text()
            )

    def _remote_file(self, relative: str) -> str | None:
        show = self._git(None, ["show", f"main:{relative}"], self.bare)
        if show.returncode != 0:
            return None
        return show.stdout

    def _publish_branch(self, work: Path, branch: str) -> None:
        self._check_git(None, ["branch", branch], work)
        self._check_git(None, ["push", "origin", branch], work)

    def test_settings_filter_keeps_git_ssh_command_for_a_trusted_project(self) -> None:
        env = apply_trusted_project_env(
            {"PATH": "/usr/bin"},
            {"env": {"GIT_SSH_COMMAND": str(self.attacker), "NOT A NAME": "x", "BAD": "a\0b"}},
        )
        self.assertEqual(env["GIT_SSH_COMMAND"], str(self.attacker))
        self.assertNotIn("NOT A NAME", env)
        self.assertNotIn("BAD", env)

    def _assert_commit_and_push_is_safe(self, scripts: list[str], attack_env: dict[str, str], repo_ssh: str | None) -> None:
        work = self._init_work("work")
        if repo_ssh is not None:
            self._check_git(None, ["config", "core.sshCommand", repo_ssh], work)
        (work / "pending.txt").write_text("uncommitted work\n")
        env = self._settings_env(attack_env)
        results = self._run_scripts(scripts, work, env)
        self._assert_attacker_did_not_run()
        failed = [result for result in results if result.returncode != 0]
        if failed:
            detail = "\n".join(f"{result.stderr}\n{result.stdout}" for result in failed)
            self.fail("skill transport command failed after the attacker command was suppressed\n" + detail)
        self.assertEqual(self._remote_file("pending.txt"), "uncommitted work\n")

    def test_run_push_ignores_settings_git_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(
            run_commit_and_push_scripts(),
            {"GIT_SSH_COMMAND": str(self.attacker)},
            None,
        )

    def test_run_push_ignores_settings_git_ssh(self) -> None:
        self._assert_commit_and_push_is_safe(
            run_commit_and_push_scripts(),
            {"GIT_SSH": str(self.attacker)},
            None,
        )

    def test_run_push_ignores_repo_core_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(run_commit_and_push_scripts(), {}, str(self.attacker))

    def test_run_push_ignores_settings_git_config_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(
            run_commit_and_push_scripts(),
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.sshCommand",
                "GIT_CONFIG_VALUE_0": str(self.attacker),
            },
            None,
        )

    def test_refactor_push_ignores_settings_git_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(
            refactor_commit_and_push_scripts(),
            {"GIT_SSH_COMMAND": str(self.attacker)},
            None,
        )

    def test_refactor_push_ignores_settings_git_ssh(self) -> None:
        self._assert_commit_and_push_is_safe(
            refactor_commit_and_push_scripts(),
            {"GIT_SSH": str(self.attacker)},
            None,
        )

    def test_refactor_push_ignores_repo_core_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(refactor_commit_and_push_scripts(), {}, str(self.attacker))

    def test_refactor_push_ignores_settings_git_config_ssh_command(self) -> None:
        self._assert_commit_and_push_is_safe(
            refactor_commit_and_push_scripts(),
            {
                "GIT_CONFIG_COUNT": "1",
                "GIT_CONFIG_KEY_0": "core.sshCommand",
                "GIT_CONFIG_VALUE_0": str(self.attacker),
            },
            None,
        )

    def test_review_push_ignores_settings_git_ssh_command(self) -> None:
        work = self._init_work("review-push")
        (work / "review.txt").write_text("review change\n")
        self._check_git(None, ["add", "-A"], work)
        self._check_git(None, ["commit", "-qm", "unpushed"], work)
        env = self._settings_env({"GIT_SSH_COMMAND": str(self.attacker)})
        results = self._run_scripts(review_push_scripts(), work, env)
        self._assert_attacker_did_not_run()
        self.assertTrue(all(result.returncode == 0 for result in results), results[0].stderr)
        self.assertEqual(self._remote_file("review.txt"), "review change\n")

    def test_review_fetch_ignores_settings_git_ssh_command(self) -> None:
        work = self._init_work("review-fetch")
        self._publish_branch(work, "shift-1")
        self._publish_branch(work, "shift-build-1")
        clone = self.root / "review-fetch-clone"
        self._check_git(None, ["clone", "-q", str(self.bare), str(clone)], self.root)
        self._check_git(None, ["remote", "set-url", "origin", self.origin], clone)
        env = self._settings_env({"GIT_SSH_COMMAND": str(self.attacker)})
        results = self._run_scripts(review_fetch_scripts(), clone, env)
        self._assert_attacker_did_not_run()
        failed = [result for result in results if result.returncode != 0]
        if failed:
            detail = "\n".join(result.stderr for result in failed)
            self.fail("review fetch still failed\n" + detail)
        for branch in ("shift-1", "shift-build-1"):
            show = self._git(None, ["rev-parse", f"origin/{branch}"], clone)
            self.assertEqual(show.returncode, 0, show.stderr)

    def test_https_origin_does_not_run_git_ssh_command(self) -> None:
        # HTTPS never consults GIT_SSH_COMMAND. The push itself is refused by
        # the closed local port; the attacker command still must not run.
        work = self._init_work(
            "https-work",
            origin="https://127.0.0.1:9/owner/repo.git",
            publish=False,
        )
        (work / "pending.txt").write_text("uncommitted work\n")
        env = self._settings_env({"GIT_SSH_COMMAND": str(self.attacker)})
        self._run_scripts(run_commit_and_push_scripts(), work, env)
        self._assert_attacker_did_not_run()


if __name__ == "__main__":
    unittest.main(verbosity=2)
