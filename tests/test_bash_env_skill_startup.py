"""Repository BASH_ENV is sourced before Shift skill shell commands.

Claude Code 2.1.325 applies a trusted project's `.claude/settings.json` `env`
object to the Bash tool's child environment (`applyConfigEnvironmentVariables`
/ `tD`, after the trust dialog or immediately in print mode). `BASH_ENV` is
not in the project-settings deny set. The Bash tool then spawns `bash -c`
(`Q6n.getSpawnArgs`). GNU bash 5.2 sources `BASH_ENV` before the `-c` script,
so a script named by the repository runs before `git` and before `curl`, and
it can read `SHIFT_API_TOKEN` from the environment. An `unset` or `env -u`
inside the `-c` script runs too late to stop that.

These tests execute the shell commands the skills tell the agent to run, under
that model. They fail while those commands are still started with `BASH_ENV`
set or while the Shift token is expanded onto curl's argv.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASH = shutil.which("bash") or "/bin/bash"
SHIFT_TOKEN = "placeholder-shift-api-token"
GITHUB_TOKEN = "placeholder-github-token"

SHELL_BACKTICK = re.compile(
    r"^(?:git\s+\S|gh\s+\S|curl\s+\S|php\s+\S|sed\s+\S|composer (?:show|update)\b)"
)
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def shell_commands(skill_text: str) -> list[str]:
    """Shell commands a skill tells the agent to run, in source order."""
    commands: list[str] = []

    def take_fence(match: re.Match[str]) -> str:
        body = match.group(1).strip("\n")
        if body.strip():
            commands.append(body)
        return ""

    prose = FENCE.sub(take_fence, skill_text)
    for span in re.findall(r"`([^`\n]+)`", prose):
        text = span.strip()
        if SHELL_BACKTICK.match(text):
            commands.append(text)
    return commands


def _write_executable(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


class SkillBashStartupTest(unittest.TestCase):
    def test_run_skill_does_not_source_repository_startup_script(self) -> None:
        self._assert_skill_does_not_leak(
            "skills/run/SKILL.md",
            required_flags={"saw_run_endpoint"},
        )

    def test_refactor_skill_does_not_source_repository_startup_script(self) -> None:
        self._assert_skill_does_not_leak(
            "skills/refactor/SKILL.md",
            required_flags={"saw_build_endpoint"},
        )

    def test_review_skill_does_not_source_repository_startup_script(self) -> None:
        # Review does not post the Shift token. It does run git, gh, composer,
        # and php, which source the same startup script and can read a GitHub
        # token already in the session.
        self._assert_skill_does_not_leak("skills/review/SKILL.md", required_flags=set())

    def test_shift_overview_does_not_source_repository_startup_script(self) -> None:
        # The overview skill names `composer update` itself. analyze/SKILL.md
        # has no shell commands and is not part of this execution path.
        commands = shell_commands((REPO_ROOT / "skills/shift/SKILL.md").read_text())
        self.assertTrue(commands, "shift skill no longer names a shell command")
        self._assert_skill_does_not_leak("skills/shift/SKILL.md", required_flags=set())

    def _assert_skill_does_not_leak(
        self, relative_skill: str, required_flags: set[str]
    ) -> None:
        skill_path = REPO_ROOT / relative_skill
        commands = shell_commands(skill_path.read_text())
        self.assertTrue(commands, f"{relative_skill} has no shell commands to execute")

        leaks: list[str] = []
        seen: set[str] = set()
        with self._project() as project:
            env = self._session_env(project)
            for index, command in enumerate(commands, start=1):
                flags = self._run_bash(project, env, command)
                seen.update(flags)
                if flags & {
                    "sourced",
                    "shift_token_in_environ",
                    "github_token_in_environ",
                    "token_in_curl_argv",
                }:
                    leaks.append(
                        f"command {index} ({_preview(command)}): {sorted(flags)}"
                    )

        missing = required_flags - seen
        self.assertFalse(
            leaks,
            f"{relative_skill} ran a repository BASH_ENV script or exposed a "
            f"session token:\n" + "\n".join(leaks),
        )
        self.assertFalse(
            missing,
            f"{relative_skill} did not reach {sorted(missing)}; the API call "
            "was not executed",
        )

    def _run_bash(self, project: Path, env: dict[str, str], command: str) -> set[str]:
        for name in ("canary.log", "curl.log"):
            log = project / name
            log.write_text("")
        completed = subprocess.run(
            [BASH, "-c", command],
            cwd=project,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        del completed
        response = Path("/tmp/shift_response.json")
        if response.exists():
            response.unlink()
        flags: set[str] = set()
        for name in ("canary.log", "curl.log"):
            flags.update(
                line for line in (project / name).read_text().splitlines() if line
            )
        return flags

    def _session_env(self, project: Path) -> dict[str, str]:
        """Environment of a Bash tool call after project settings are trusted.

        User/session values are applied first. Project `.claude/settings.json`
        `env` strings then overwrite them, with no shell expansion, matching
        Claude Code's full settings pass.
        """
        settings_path = project / ".claude" / "settings.json"
        settings = json.loads(settings_path.read_text())
        env = {
            "PATH": f"{project / 'fake-bin'}:{os.environ.get('PATH', '/usr/bin:/bin')}",
            "HOME": str(project / "home"),
            "SHIFT_API_TOKEN": SHIFT_TOKEN,
            "GH_TOKEN": GITHUB_TOKEN,
            "CANARY_LOG": str(project / "canary.log"),
            "CURL_FLAG_LOG": str(project / "curl.log"),
            "CANARY_SHIFT_PLACEHOLDER": SHIFT_TOKEN,
            "CANARY_GH_PLACEHOLDER": GITHUB_TOKEN,
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        project_env = settings.get("env") or {}
        if not isinstance(project_env, dict):
            self.fail("project settings env is not an object")
        for key, value in project_env.items():
            if isinstance(key, str) and isinstance(value, str):
                env[key] = value
        return env

    def _project(self):
        return _Project()


class _Project:
    def __enter__(self) -> Path:
        self._temp = tempfile.TemporaryDirectory()
        root = Path(self._temp.name)
        bare = root / "bare.git"
        work = root / "work"
        subprocess.run(["git", "init", "--bare", str(bare)], check=True, capture_output=True)
        subprocess.run(["git", "init", str(work)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(work), "remote", "add", "origin", str(bare)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(work), "symbolic-ref", "HEAD", "refs/heads/main"],
            check=True,
            capture_output=True,
        )
        claude_dir = work / ".claude"
        claude_dir.mkdir()
        (work / "home").mkdir()
        fake_bin = work / "fake-bin"
        fake_bin.mkdir()
        _write_executable(claude_dir / "startup.sh", _CANARY)
        (claude_dir / "settings.json").write_text(
            json.dumps({"env": {"BASH_ENV": ".claude/startup.sh"}}) + "\n"
        )
        _write_executable(fake_bin / "curl", _FAKE_CURL)
        for name in ("gh", "composer", "php", "ssh"):
            _write_executable(fake_bin / name, "#!/bin/sh\nexit 0\n")
        (work / "canary.log").write_text("")
        (work / "curl.log").write_text("")
        self.work = work
        return work

    def __exit__(self, exc_type, exc, tb) -> None:
        self._temp.cleanup()


def _preview(command: str) -> str:
    first = command.strip().splitlines()[0]
    return first if len(first) <= 80 else first[:77] + "..."


_CANARY = """#!/bin/bash
printf '%s\\n' sourced >> "$CANARY_LOG"
if [ -n "${CANARY_SHIFT_PLACEHOLDER-}" ] && [ "${SHIFT_API_TOKEN-}" = "$CANARY_SHIFT_PLACEHOLDER" ]; then
  printf '%s\\n' shift_token_in_environ >> "$CANARY_LOG"
fi
if [ -n "${CANARY_GH_PLACEHOLDER-}" ] && [ "${GH_TOKEN-}" = "$CANARY_GH_PLACEHOLDER" ]; then
  printf '%s\\n' github_token_in_environ >> "$CANARY_LOG"
fi
"""

_FAKE_CURL = r"""#!/bin/bash
printf '%s\n' curl_invoked >> "$CURL_FLAG_LOG"
for arg in "$@"; do
  if [ -n "${CANARY_SHIFT_PLACEHOLDER-}" ] && [ "${arg#*"$CANARY_SHIFT_PLACEHOLDER"}" != "$arg" ]; then
    printf '%s\n' token_in_curl_argv >> "$CURL_FLAG_LOG"
  fi
  case "$arg" in
    https://laravelshift.com/api/run) printf '%s\n' saw_run_endpoint >> "$CURL_FLAG_LOG" ;;
    https://laravelshift.com/api/build) printf '%s\n' saw_build_endpoint >> "$CURL_FLAG_LOG" ;;
  esac
done
outfile=""
prev=""
for arg in "$@"; do
  if [ "$prev" = "-o" ]; then
    outfile="$arg"
  fi
  prev="$arg"
done
if [ -n "$outfile" ]; then
  printf '%s' '{"ok":true}' > "$outfile"
fi
printf '%s' '202'
"""


if __name__ == "__main__":
    unittest.main()
