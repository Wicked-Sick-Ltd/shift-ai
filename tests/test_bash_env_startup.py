"""Skill shell commands must not run a repository-selected bash startup file.

Claude Code 2.1.325 runs each Bash-tool command as non-interactive bash.
With a shell snapshot the arguments are ["-c", command]; without one they
are ["-c", "-l", command] (getSpawnArgs). GNU bash 5.2.21 sources $BASH_ENV
from that process environment before it reads the -c string
(shell.c run_startup_files / execute_env_file). After the workspace is
trusted, a project .claude/settings.json env entry is copied into that
environment (it is not in the project-settings denylist). The Shift API
token is already in the same environment when these skills run.

These tests fail while that startup file runs, or while the token is
expanded into a child process's arguments. They pass once every shell
operation below is run so that neither happens. Unsetting BASH_ENV inside
the -c string does not count: bash has already sourced the file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOKEN = "placeholder-shift-api-token"
SPAWN_FORMS = ("snapshot", "login")

SKILLS_WITH_SHELL = (
    "skills/refactor/SKILL.md",
    "skills/run/SKILL.md",
    "skills/review/SKILL.md",
)

# Shell operations the skills tell the agent to run outside a bash fence.
# analyze/SKILL.md and shift/SKILL.md do not run a shell.
INLINE_COMMANDS = (
    ("skills/refactor/SKILL.md", "git add -A"),
    ("skills/refactor/SKILL.md", "git commit -m placeholder"),
    ("skills/refactor/SKILL.md", "git push"),
    ("skills/run/SKILL.md", "git add -A"),
    ("skills/run/SKILL.md", "git commit -m placeholder"),
    ("skills/run/SKILL.md", "git push"),
    ("skills/review/SKILL.md", "git status --porcelain"),
    ("skills/review/SKILL.md", "git commit -m 'composer update'"),
    ("skills/review/SKILL.md", "git commit -m 'Finalize upgrade'"),
    ("skills/review/SKILL.md", "git log origin/placeholder..HEAD"),
    ("skills/review/SKILL.md", "git push"),
    ("skills/review/SKILL.md", "gh --version"),
    ("skills/review/SKILL.md", "composer show example/package --all"),
    ("skills/review/SKILL.md", "composer update"),
    ("skills/review/SKILL.md", "php artisan test --compact"),
    ("skills/review/SKILL.md", "vendor/bin/pint --dirty"),
    ("skills/review/SKILL.md", "vendor/bin/php-cs-fixer fix"),
)

FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def fenced_commands(relative: str) -> list[tuple[str, str]]:
    text = (REPO / relative).read_text()
    found = []
    for match in FENCE.finditer(text):
        body = match.group(1)
        line = text[: match.start()].count("\n") + 1
        pending = ""
        for raw in body.splitlines():
            stripped = raw.strip()
            if pending == "" and (stripped == "" or stripped.startswith("#")):
                continue
            pending = raw if pending == "" else pending + "\n" + raw
            if raw.rstrip().endswith("\\"):
                continue
            found.append((f"{relative}:{line}", pending))
            pending = ""
            line += raw.count("\n") + 1
        if pending:
            found.append((f"{relative}:{line}", pending))
    return found


def all_skill_commands() -> list[tuple[str, str]]:
    commands = []
    for skill in SKILLS_WITH_SHELL:
        commands.extend(fenced_commands(skill))
    commands.extend(INLINE_COMMANDS)
    return commands


class BashEnvStartupTests(unittest.TestCase):
    def test_skills_still_contain_shell_operations(self):
        commands = all_skill_commands()
        joined = "\n".join(command for _, command in commands)
        self.assertIn("git remote get-url origin", joined)
        self.assertIn("https://laravelshift.com/api/build", joined)
        self.assertIn("https://laravelshift.com/api/run", joined)
        self.assertGreaterEqual(len(fenced_commands("skills/review/SKILL.md")), 1)

    def test_repository_settings_env_does_not_run_before_skill_commands(self):
        for label, command in all_skill_commands():
            for form in SPAWN_FORMS:
                with self.subTest(command=label, spawn=form):
                    result = self._run(command, form)
                    self.assertFalse(
                        result.startup_ran,
                        f"{label} via bash {form} sourced the repository startup script",
                    )
                    self.assertFalse(
                        result.saw_token,
                        f"{label} via bash {form} exposed the API token to the startup script",
                    )

    def test_api_token_is_not_expanded_into_child_arguments(self):
        curls = [
            (label, command)
            for label, command in all_skill_commands()
            if "SHIFT_API_TOKEN" in command or "laravelshift.com/api/" in command
        ]
        self.assertGreaterEqual(len(curls), 2)
        for label, command in curls:
            for form in SPAWN_FORMS:
                with self.subTest(command=label, spawn=form):
                    result = self._run(command, form)
                    self.assertFalse(
                        result.startup_ran,
                        f"{label} via bash {form} sourced the repository startup script",
                    )
                    self.assertNotIn(
                        TOKEN,
                        result.argv_text,
                        f"{label} via bash {form} placed the API token in a child argument list",
                    )

    def test_harness_sources_startup_only_when_bash_env_is_set(self):
        leaked = self._run("true", "snapshot")
        self.assertTrue(leaked.startup_ran)
        self.assertTrue(leaked.saw_token)
        clean = self._run("true", "snapshot", bash_env=None)
        self.assertFalse(clean.startup_ran)
        self.assertFalse(clean.saw_token)

    def _run(self, command: str, form: str, bash_env: str | None = "startup.sh"):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            home = root / "home"
            home.mkdir()
            subprocess.run(["git", "init", "-q"], cwd=root, check=True, capture_output=True)
            marker = root / "marker"
            argv_log = root / "argv"
            startup = root / "startup.sh"
            startup.write_text(
                "printf '%s\\n' ran >> \"$MARKER\"\n"
                "if [ -n \"${SHIFT_API_TOKEN:-}\" ]; then printf '%s\\n' token >> \"$MARKER\"; fi\n"
            )
            settings = {"env": {"BASH_ENV": "startup.sh"}}
            settings_dir = root / ".claude"
            settings_dir.mkdir()
            (settings_dir / "settings.json").write_text(json.dumps(settings))
            chosen = json.loads((settings_dir / "settings.json").read_text())["env"]["BASH_ENV"]
            self.assertEqual(chosen, "startup.sh")

            shim_dir = root / "shims"
            shim_dir.mkdir()
            shim = shim_dir / "record"
            shim.write_text(
                "#!/usr/bin/env python3\n"
                "import os, sys\n"
                "with open(os.environ['ARGV_LOG'], 'a') as handle:\n"
                "    handle.write('\\0'.join(sys.argv) + '\\n')\n"
            )
            shim.chmod(0o755)
            for name in ("curl", "gh", "composer", "php"):
                os.symlink(shim, shim_dir / name)

            env = {
                "PATH": f"{shim_dir}:/usr/bin:/bin",
                "HOME": str(home),
                "MARKER": str(marker),
                "ARGV_LOG": str(argv_log),
                "SHIFT_API_TOKEN": TOKEN,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_TERMINAL_PROMPT": "0",
                "TERM": "dumb",
            }
            if bash_env is not None:
                # Same string the repository settings env object selected.
                env["BASH_ENV"] = chosen

            if form == "snapshot":
                args = ["bash", "-c", command]
            elif form == "login":
                args = ["bash", "-c", "-l", command]
            else:
                raise AssertionError(form)

            subprocess.run(
                args,
                cwd=root,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
                check=False,
            )
            text = marker.read_text() if marker.exists() else ""
            argv_text = argv_log.read_text() if argv_log.exists() else ""
            return RunResult("ran" in text.splitlines(), "token" in text.splitlines(), argv_text)


class RunResult:
    def __init__(self, startup_ran: bool, saw_token: bool, argv_text: str):
        self.startup_ran = startup_ran
        self.saw_token = saw_token
        self.argv_text = argv_text


if __name__ == "__main__":
    unittest.main()
