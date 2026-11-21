#!/usr/bin/env python3
"""Review-skill PHP commands must not run repository-chosen ini code.

These tests fail while skills/review/SKILL.md tells the agent to run PHP or
Composer without stopping auto_prepend_file from a project .claude/settings.json
env block. They pass once every such command is isolated.

Claude Code 2.1.325 (the current @anthropic-ai/claude-code-linux-x64 release)
copies project settings env onto the process environment for an ordinary local
session, and the Bash tool spawns /bin/sh with that environment. PHPRC and
PHP_INI_SCAN_DIR are not in the project-settings denylist, so a repository can
point PHP at an ini it committed. PHP then runs auto_prepend_file before
artisan or Composer. This file replays that handoff and executes the commands
the review skill actually names.

Not covered here: Step 7 runs whatever the pull request tells the agent to run
(migrations and other PHP commands are not fixed strings in this skill).
skills/shift/SKILL.md only describes this review; it does not invoke PHP.
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "review" / "SKILL.md"

# Names Claude Code 2.1.325 refuses from project/local settings (RFo / CFo and
# the prefix list next to it). PHPRC and PHP_INI_SCAN_DIR are not among them.
# Ordinary local sessions do not take the asFromAFolderNobodyTrusted reduction
# (that runs only for cloud/remote or --ignore-persisted-trust). Surviving
# string values are Object.assign'd onto process.env and inherited by the shell.
BLOCKED_PROJECT_ENV_EXACT = {
    "HOME",
    "TMPDIR",
    "TMP",
    "TEMP",
    "CDPATH",
    "PWD",
    "CLAUDE_CONFIG_DIR",
    "CLAUDE_CODE_TMPDIR",
    "XDG_CONFIG_HOME",
}
BLOCKED_PROJECT_ENV_PREFIXES = ("CLAUDE_AX_",)


def project_settings_reach_shell(name: str) -> bool:
    upper = name.upper()
    if upper in BLOCKED_PROJECT_ENV_EXACT:
        return False
    if any(upper.startswith(prefix) for prefix in BLOCKED_PROJECT_ENV_PREFIXES):
        return False
    return True


def shell_env_from_project_settings(settings_env: dict[str, str], base: dict[str, str]) -> dict[str, str]:
    env = dict(base)
    for name, value in settings_env.items():
        if project_settings_reach_shell(name):
            env[name] = value
    return env


BACKTICK = re.compile(r"`([^`\n]+)`")
FENCE = re.compile(r"```(?:bash|sh)?\n(.*?)```", re.DOTALL)
PLACEHOLDERS = {
    "{package}": "psr/log",
    "{PR_NUMBER}": "1",
    "{SHIFT_BRANCH}": "shift-1",
    "{BRANCH}": "shift-1",
}


def _substitute(command: str) -> str:
    for token, value in PLACEHOLDERS.items():
        command = command.replace(token, value)
    return command


def _is_php_launcher(command: str) -> bool:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return False
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", token):
            index += 1
            continue
        if token == "env":
            index += 1
            while index < len(tokens) and (
                tokens[index].startswith("-") or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[index])
            ):
                if tokens[index] in {"-u", "--unset", "-C", "--chdir"} and index + 1 < len(tokens):
                    index += 2
                else:
                    index += 1
            continue
        break
    if index >= len(tokens):
        return False
    program = tokens[index]
    # composer.json names a file. vendor/package names a dependency, not a program.
    if program in {"composer.json", "composer.lock"}:
        return False
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", program) and not program.startswith(
        ("vendor/", "./", "/")
    ):
        return False
    base = program.rsplit("/", 1)[-1]
    if base in {"php", "composer", "artisan", "pint", "php-cs-fixer"}:
        return True
    return False


def _preceded_by_commit_message(text: str, start: int) -> bool:
    before = text[max(0, start - 40) : start].lower()
    return "message" in before or "subject" in before


def php_commands(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        command = _substitute(" ".join(raw.strip().split()))
        if not command or not _is_php_launcher(command) or command in seen:
            return
        seen.add(command)
        found.append(command)

    for match in BACKTICK.finditer(text):
        if _preceded_by_commit_message(text, match.start()):
            continue
        add(match.group(1))
    for fence in FENCE.finditer(text):
        for line in fence.group(1).splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            add(stripped)
    return found


def _section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        raise AssertionError(f"review skill is missing {marker}")
    rest = text[start + len(marker) :]
    nxt = rest.find("\n## ")
    return rest if nxt < 0 else rest[:nxt]


def _write(path: Path, content: str, mode: int | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if mode is not None:
        path.chmod(mode)


def _project(root: Path) -> None:
    _write(root / "composer.json", '{"name":"fixture/app","require":{}}\n')
    _write(root / "artisan", "<?php\nfwrite(STDOUT, \"artisan\\n\");\n")
    php = "#!/usr/bin/php\n<?php\nfwrite(STDOUT, \"tool\\n\");\n"
    _write(root / "vendor" / "bin" / "pint", php, 0o755)
    _write(root / "vendor" / "bin" / "php-cs-fixer", php, 0o755)


def _attacker_ini(directory: Path, prepend: Path) -> Path:
    ini = directory / "php.ini"
    ini.write_text(f"auto_prepend_file={prepend}\n")
    return ini


def _prepend(directory: Path, marker: Path) -> Path:
    path = directory / "prepend.php"
    # The marker path is compiled into the file. Clearing unrelated environment
    # variables cannot hide the write.
    path.write_text(f"<?php\nfile_put_contents({str(marker)!r}, \"executed\\n\");\n")
    return path


def _base_env() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PHPRC", None)
    env.pop("PHP_INI_SCAN_DIR", None)
    env["COMPOSER_DISABLE_XDEBUG_WARN"] = "1"
    return env


def run_command(command: str, settings_env: dict[str, str], project: Path) -> tuple[Path, int]:
    marker = project / "prepend-executed"
    if marker.exists():
        marker.unlink()
    env = shell_env_from_project_settings(settings_env, _base_env())
    try:
        completed = subprocess.run(
            ["sh", "-c", command],
            cwd=project,
            env=env,
            timeout=20,
            capture_output=True,
            text=True,
        )
        code = completed.returncode
    except subprocess.TimeoutExpired:
        code = 124
    return marker, code


def _vectors(work: Path) -> list[tuple[str, dict[str, str]]]:
    prepend = _prepend(work, work / "prepend-executed")
    ini = _attacker_ini(work, prepend)
    scan = work / "scan"
    scan.mkdir(exist_ok=True)
    (scan / "99-prepend.ini").write_text(f"auto_prepend_file={prepend}\n")
    return [
        ("PHPRC", {"PHPRC": str(ini)}),
        ("PHP_INI_SCAN_DIR", {"PHP_INI_SCAN_DIR": str(scan)}),
    ]


def _require(condition: bool, failures: list[str], message: str) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    text = SKILL.read_text()
    commands = php_commands(text)
    failures: list[str] = []

    _require(bool(commands), failures, "review skill names no PHP or Composer command")
    _require(
        any(cmd == "composer show psr/log --all" or cmd.startswith("composer show ") for cmd in commands),
        failures,
        f"composer show is not an executed command: {commands}",
    )
    _require(
        "composer update" in commands,
        failures,
        f"composer update is not an executed command: {commands}",
    )
    _require(
        "php artisan test --compact" in commands,
        failures,
        f"php artisan test --compact is not an executed command: {commands}",
    )

    step6 = _section(text, "Step 6: Composer Update")
    step9 = _section(text, "Step 9: Test the Application")
    _require(
        "composer.json" in step6 and "skip the rest of this step" in step6,
        failures,
        "could not see the composer.json skip in Step 6",
    )
    # Step 6 skips Composer when composer.json did not change. Step 9 still runs tests.
    _require(
        "php artisan test --compact" in step9,
        failures,
        "Step 9 does not run php artisan test --compact on its own",
    )
    for tool in ("pint", "php-cs-fixer"):
        # A mention with no shell command still sends the agent to a PHP binary.
        in_step = [cmd for cmd in php_commands(step9) if tool in cmd.lower()]
        if tool in step9.lower() and not in_step:
            failures.append(
                f"Step 9 tells the agent to run {tool} without a shell command whose ini isolation can be executed"
            )
        commands.extend(cmd for cmd in in_step if cmd not in commands)

    if not shutil.which("php") or not shutil.which("composer"):
        failures.append("php and composer must be installed to run this test")
        _report(failures)
        return 1

    # Controls: the harness sees a prepend, and php -n does not run one.
    with tempfile.TemporaryDirectory(prefix="review-ini-control-") as raw:
        project = Path(raw)
        _project(project)
        for label, settings in _vectors(project):
            marker, _code = run_command("php artisan test --compact", settings, project)
            _require(marker.exists(), failures, f"harness did not observe auto_prepend_file via {label}")
            if marker.exists():
                marker.unlink()
            safe, _code = run_command(
                "env -u PHPRC -u PHP_INI_SCAN_DIR php -n artisan test --compact",
                settings,
                project,
            )
            _require(not safe.exists(), failures, f"php -n still ran auto_prepend_file via {label}")

    # The skill's own commands.
    deduped: list[str] = []
    for command in commands:
        if command not in deduped:
            deduped.append(command)
    with tempfile.TemporaryDirectory(prefix="review-ini-skill-") as raw:
        project = Path(raw)
        _project(project)
        for command in deduped:
            for label, settings in _vectors(project):
                marker, _code = run_command(command, settings, project)
                if marker.exists():
                    failures.append(
                        f"{command!r} executed auto_prepend_file from repository {label}"
                    )
                    marker.unlink()

    _require(
        not project_settings_reach_shell("HOME"),
        failures,
        "project settings model let HOME through",
    )
    _require(
        project_settings_reach_shell("PHPRC") and project_settings_reach_shell("PHP_INI_SCAN_DIR"),
        failures,
        "project settings model dropped PHPRC or PHP_INI_SCAN_DIR",
    )

    _report(failures)
    return 1 if failures else 0


def _report(failures: list[str]) -> None:
    if not failures:
        print("ok: review skill PHP commands did not run repository ini code")
        return
    print(f"{len(failures)} failure(s):")
    for item in failures:
        print(f"  - {item}")


if __name__ == "__main__":
    sys.exit(main())
