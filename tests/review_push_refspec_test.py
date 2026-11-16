#!/usr/bin/env python3
"""The review skill's merge push must publish only the reviewed branch.

After the user agrees to merge, skills/review/SKILL.md tells the agent to
publish unpushed commits. These tests take that push command from the skill
and run it, as bash, against a local origin. The environment is the one a
trusted Claude Code session copies out of a project's .claude/settings.json
env block into the Bash tool: Git's configuration variables
(GIT_CONFIG_COUNT / GIT_CONFIG_KEY_n / GIT_CONFIG_VALUE_n, and
GIT_CONFIG_PARAMETERS).

A bare `git push` follows remote.origin.mirror and remote.origin.push from
that environment. Mirror force-updates every ref the clone has and deletes
every remote ref it does not. A configured push refspec chooses which
branches are force-updated. The push is safe only when the reviewed branch
is the only ref that changes, for every one of those environments.

The placeholders {branch} and {BRANCH} are filled in the way the skill's
other steps spell a branch name, then the command is parsed by bash. Shell
forms such as ${branch} are left for bash. The branch shift-1;id is a legal
ref; substituting it into an unquoted word splits the command.

skills/run/SKILL.md and skills/refactor/SKILL.md say to push the current
branch and do not give a command. They are scanned so a bare `git push`
added there fails, and they are not executed.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
REVIEW = SKILLS / "review" / "SKILL.md"

# Attacker-controlled settings env that Claude Code applies to Bash after the
# workspace is trusted. Values are Git config, not credentials.
ATTACKS = {
    "mirror": {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "remote.origin.mirror",
        "GIT_CONFIG_VALUE_0": "true",
    },
    "push_refspec": {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "remote.origin.push",
        "GIT_CONFIG_VALUE_0": "+refs/heads/*:refs/heads/*",
    },
    "mirror_and_push_refspec": {
        "GIT_CONFIG_COUNT": "2",
        "GIT_CONFIG_KEY_0": "remote.origin.mirror",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_CONFIG_KEY_1": "remote.origin.push",
        "GIT_CONFIG_VALUE_1": "+refs/heads/*:refs/heads/*",
    },
    "parameters_mirror": {
        "GIT_CONFIG_PARAMETERS": "'remote.origin.mirror=true'",
    },
}


def _skill_push_commands(path: Path) -> list[str]:
    """Shell snippets in a skill that invoke git push."""
    text = path.read_text()
    if path == REVIEW:
        start = text.index("If the user confirms they want to merge:")
        end = text.index("Merge using the appropriate method", start)
        text = text[start:end]
    commands: list[str] = []
    for body in re.findall(r"```(?:bash|sh)?\n(.*?)```", text, re.S):
        if _is_git_push(body):
            commands.append(body.strip())
    for body in re.findall(r"`([^`\n]+)`", text):
        if _is_git_push(body):
            commands.append(body.strip())
    return commands


def _is_git_push(body: str) -> bool:
    """True when a shell snippet runs git push, not git log or git status."""
    stripped = re.sub(r"'[^']*'|\"[^\"]*\"", " ", body)
    return re.search(r"\bgit\s+(?:-c\s+\S+\s+)*push\b", stripped) is not None


def _render(command: str, branch: str) -> str:
    """Substitute skill placeholders without touching ${branch}."""
    command = re.sub(r"(?<!\$)\{BRANCH\}", branch, command)
    command = re.sub(r"(?<!\$)\{branch\}", branch, command)
    return command


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = _clean_env()
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env,
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"git {args} failed\n{result.stdout}\n{result.stderr}")
    return result


def _clean_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_AUTHOR_NAME"] = "Review Push Test"
    env["GIT_AUTHOR_EMAIL"] = "review-push-test@example.com"
    env["GIT_COMMITTER_NAME"] = env["GIT_AUTHOR_NAME"]
    env["GIT_COMMITTER_EMAIL"] = env["GIT_AUTHOR_EMAIL"]
    if extra:
        env.update(extra)
    return env


def _refs(repo: Path) -> dict[str, str]:
    result = _git(["show-ref"], repo, check=False)
    refs: dict[str, str] = {}
    for line in result.stdout.splitlines():
        sha, ref = line.split(" ", 1)
        refs[ref] = sha
    return refs


def _fixture(branch: str) -> tuple[Path, Path, Path]:
    """Origin with main, an unrelated branch, a tag, and the reviewed branch.

    The clone is on the reviewed branch with one unpushed commit. Local main
    points at an older commit than origin, and the local tag is gone, so a
    mirror push force-updates main and deletes the tag and the unrelated
    branch.
    """
    tmp = Path(tempfile.mkdtemp(prefix="review-push-"))
    origin = tmp / "origin.git"
    clone = tmp / "clone"
    seed = tmp / "seed"
    _git(["init", "--bare", "-q", str(origin)], tmp)
    _git(["symbolic-ref", "HEAD", "refs/heads/main"], origin)
    _git(["init", "-q", "-b", "main", str(seed)], tmp)
    (seed / "a").write_text("a\n")
    _git(["add", "a"], seed)
    _git(["commit", "-qm", "A"], seed)
    _git(["tag", "v1"], seed)
    (seed / "b").write_text("b\n")
    _git(["add", "b"], seed)
    _git(["commit", "-qm", "B"], seed)
    _git(["branch", "unrelated"], seed)
    (seed / "s").write_text("s\n")
    _git(["add", "s"], seed)
    _git(["commit", "-qm", "S1"], seed)
    _git(["update-ref", f"refs/heads/{branch}", "HEAD"], seed)
    _git(["remote", "add", "origin", str(origin)], seed)
    _git(["push", "-q", "origin", "main", "unrelated", f"refs/heads/{branch}", "v1"], seed)
    _git(["clone", "-q", str(origin), str(clone)], tmp)
    _git(["checkout", "-q", branch], clone)
    (clone / "s2").write_text("s2\n")
    _git(["add", "s2"], clone)
    _git(["commit", "-qm", "S2"], clone)
    _git(["branch", "-f", "main", "origin/main~1"], clone)
    _git(["tag", "-d", "v1"], clone, check=False)
    return tmp, origin, clone


class ReviewPushRefspecTest(unittest.TestCase):
    def test_review_skill_has_one_merge_push(self) -> None:
        commands = _skill_push_commands(REVIEW)
        self.assertEqual(
            len(commands),
            1,
            f"expected the merge steps to name one git push, found {commands!r}",
        )

    def test_other_skills_do_not_bare_push(self) -> None:
        """run and refactor describe a push but do not give a git push command."""
        for path in sorted(SKILLS.glob("*/SKILL.md")):
            if path == REVIEW:
                continue
            pushes = _skill_push_commands(path)
            self.assertEqual(pushes, [], f"{path.relative_to(ROOT)} contains git push: {pushes!r}")

    def test_merge_push_updates_only_the_reviewed_branch(self) -> None:
        commands = _skill_push_commands(REVIEW)
        self.assertEqual(len(commands), 1, commands)
        command = commands[0]
        cases = [
            ("shift-1", "mirror"),
            ("shift-1", "push_refspec"),
            ("shift-1", "mirror_and_push_refspec"),
            ("shift-1", "parameters_mirror"),
            # Legal ref. An unquoted textual substitution of this name splits
            # the shell command and publishes a different branch.
            ("shift-1;id", "mirror_and_push_refspec"),
        ]
        failures: list[str] = []
        for branch, attack in cases:
            problem = self._run_case(command, branch, attack)
            if problem:
                failures.append(f"{attack} branch {branch!r}: {problem}")
        self.assertEqual(failures, [], "\n".join(failures))

    def _run_case(self, command: str, branch: str, attack: str) -> str | None:
        tmp, origin, clone = _fixture(branch)
        try:
            before = _refs(origin)
            rendered = _render(command, branch)
            env = _clean_env(ATTACKS[attack])
            env["branch"] = branch
            env["BRANCH"] = branch
            result = subprocess.run(
                ["bash", "-c", rendered],
                cwd=clone,
                env=env,
                text=True,
                capture_output=True,
            )
            after = _refs(origin)
            local = _git(["rev-parse", "HEAD"], clone).stdout.strip()
            reviewed = f"refs/heads/{branch}"
            if result.returncode != 0:
                return f"push exited {result.returncode}: {result.stderr.strip()}"
            if after.get(reviewed) != local:
                return (
                    f"reviewed ref {reviewed} is {after.get(reviewed)}, "
                    f"local HEAD is {local}\n{result.stderr.strip()}"
                )
            if set(after) != set(before):
                added = sorted(set(after) - set(before))
                removed = sorted(set(before) - set(after))
                return f"ref list changed; added {added}, removed {removed}\n{result.stderr.strip()}"
            changed = sorted(ref for ref, sha in before.items() if after[ref] != sha and ref != reviewed)
            if changed:
                detail = ", ".join(f"{ref} {before[ref][:7]}->{after[ref][:7]}" for ref in changed)
                return f"updated refs other than the reviewed branch: {detail}\n{result.stderr.strip()}"
            return None
        finally:
            shutil.rmtree(tmp)


if __name__ == "__main__":
    unittest.main()
