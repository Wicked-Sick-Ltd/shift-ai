"""The GitLab and Bitbucket review procedure must test the commit it diffed.

`skills/review/SKILL.md` fetches the remote Shift branch, diffs that tip, then
checks out the local branch of the same name and later tells the developer to
merge the hosting-site request. These tests follow those commands in a local
repository. They fail while checkout stays on an older local commit, or while
the merge instruction does not name the commit that was diffed.

A commit pushed to the remote after that diff, and not fetched again, must not
become the tree that is checked out or the commit the developer is told to merge.
The same procedure is used for `shift-<n>` and, when that fetch fails, for
`shift-build-<n>`.

GitHub review uses `gh pr checkout` and is not part of this procedure.

Run from the repository root:

    python3 -m unittest tests.test_review_skill_checkout -v
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "skills" / "review" / "SKILL.md"

STALE_MARKER = "stale-tree"
REVIEWED_MARKER = "reviewed-dependency"
UNTESTED_MARKER = "untested-dependency"


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in list(env):
        if key in {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_PREFIX"}:
            env.pop(key)
    env["GIT_CONFIG_GLOBAL"] = "/dev/null"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_SYSTEM"] = "/dev/null"
    env["GIT_PAGER"] = "cat"
    env["PAGER"] = "cat"
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_AUTHOR_NAME"] = "Dev"
    env["GIT_AUTHOR_EMAIL"] = "dev@example.com"
    env["GIT_COMMITTER_NAME"] = "Dev"
    env["GIT_COMMITTER_EMAIL"] = "dev@example.com"
    return env


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=_git_env(),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {cwd} ({result.returncode})\n"
            f"{result.stdout}{result.stderr}"
        )
    return result


def _assigned_names(script: str) -> set[str]:
    """Names a skill block can carry into a later block, such as a saved commit."""
    names = set(re.findall(
        r"(?:^|[\n;])\s*(?:export\s+|declare\s+(?:-\S+\s+)?|local\s+)?([A-Za-z_][A-Za-z0-9_]*)=",
        script,
    ))
    return {
        name
        for name in names
        if not re.search(r"(TOKEN|SECRET|PASSWORD|CREDENTIAL|KEY)", name, re.I)
    }


class SkillShell:
    """Run the skill's bash blocks with variables preserved between blocks.

    Each block runs in a subshell so `set -e` cannot kill the runner. Only
    names that a block assigns are restored for the next block, which is how a
    commit recorded during fetch can be the commit checked out afterwards.
    """

    def __init__(self, cwd: Path, arguments: str):
        self.cwd = cwd
        self.env = _git_env()
        self.env["ARGUMENTS"] = arguments
        self._prelude = ""
        self._names: set[str] = set()
        self._directory = tempfile.TemporaryDirectory(prefix="review-skill-shell-")
        self._root = Path(self._directory.name)

    def close(self) -> None:
        self._directory.cleanup()

    def run(self, script: str) -> subprocess.CompletedProcess[str]:
        self._names.update(_assigned_names(script))
        script_path = self._root / "script.sh"
        prelude_path = self._root / "prelude.sh"
        state_path = self._root / "state.declare"
        script_path.write_text(script if script.endswith("\n") else script + "\n")
        prelude_path.write_text(self._prelude)
        state_path.write_text("")
        names = " ".join(sorted(self._names))
        name_loop = ""
        if names:
            name_loop = textwrap.dedent(
                f"""\
                for __name in {names}; do
                  if declare -p "$__name" >/dev/null 2>&1; then
                    declare -p "$__name" >> {state_path}
                  fi
                done
                """
            )
        wrapper = textwrap.dedent(
            f"""\
            set +e
            (
              trap 'ec=$?; set +e; : > {state_path}; {name_loop}exit $ec' EXIT
              set +e
              source {prelude_path}
              source {script_path}
            )
            exit $?
            """
        )
        result = subprocess.run(
            ["bash", "--noprofile", "--norc"],
            cwd=self.cwd,
            env=self.env,
            input=wrapper,
            text=True,
            capture_output=True,
            check=False,
            timeout=60,
        )
        if state_path.exists():
            self._prelude = state_path.read_text()
        return result


def split_steps(skill: str) -> dict[int, str]:
    steps: dict[int, str] = {}
    for part in re.split(r"(?=^## Step \d+)", skill, flags=re.M):
        match = re.match(r"## Step (\d+)", part)
        if match:
            steps[int(match.group(1))] = part
    return steps


def gitlab_bitbucket_section(step: str) -> str:
    match = re.search(r"^\*\*GitLab and Bitbucket", step, flags=re.M)
    if not match:
        raise AssertionError(
            "The review skill has no GitLab and Bitbucket section in this step:\n"
            + step[:500]
        )
    return step[match.start() :]


def bash_fences(section: str) -> list[str]:
    return [block.strip() + "\n" for block in re.findall(r"```bash\n(.*?)```", section, re.S)]


def substitute_branch(script: str, branch: str) -> str:
    return (
        script.replace("{SHIFT_BRANCH}", branch)
        .replace("{BRANCH}", branch)
        .replace("{PR_NUMBER}", "1")
    )


def first_blockquote(section: str) -> str:
    lines = section.splitlines()
    quote: list[str] = []
    started = False
    for line in lines:
        if line.startswith(">"):
            started = True
            quote.append(re.sub(r"^>\s?", "", line))
        elif started:
            break
    if not quote:
        raise AssertionError(
            "The GitLab and Bitbucket merge step has no instruction to the developer."
        )
    text = "\n".join(quote).strip()
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    return text


def rev_parse(repo: Path, revision: str) -> str | None:
    result = git(repo, "rev-parse", "--verify", "--quiet", revision, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def tracking_branch(repo: Path, number: int) -> str | None:
    for name in (f"shift-{number}", f"shift-build-{number}"):
        if rev_parse(repo, f"origin/{name}"):
            return name
    return None


class Repository:
    def __init__(self, branch: str):
        self.branch = branch
        self._directory = tempfile.TemporaryDirectory(prefix="review-skill-repo-")
        root = Path(self._directory.name)
        self.remote = root / "remote.git"
        self.dev = root / "dev"
        self.collab = root / "collab"
        git(root, "init", "-b", "main", "--bare", str(self.remote))
        git(root, "init", "-b", "main", str(self.dev))
        git(self.dev, "remote", "add", "origin", str(self.remote))
        (self.dev / "README").write_text(f"base {branch}\n")
        git(self.dev, "add", "README")
        git(self.dev, "commit", "-m", f"base {branch}")
        git(self.dev, "push", "-u", "origin", "main")
        git(self.dev, "checkout", "-b", branch)
        self._write_tree(self.dev, STALE_MARKER)
        git(self.dev, "add", "composer.json", "marker.txt")
        git(self.dev, "commit", "-m", "shift A")
        git(self.dev, "push", "-u", "origin", branch)
        self.stale = rev_parse(self.dev, "HEAD")
        assert self.stale is not None
        git(root, "clone", str(self.remote), str(self.collab))
        git(self.collab, "checkout", branch)
        self._write_tree(self.collab, REVIEWED_MARKER)
        git(self.collab, "commit", "-am", "shift B")
        git(self.collab, "push", "origin", branch)
        self.reviewed = rev_parse(self.collab, "HEAD")
        assert self.reviewed is not None
        git(self.dev, "checkout", "main")

    def close(self) -> None:
        self._directory.cleanup()

    def remove_local_branch(self) -> None:
        git(self.dev, "branch", "-D", self.branch)

    def push_untested_commit(self) -> str:
        self._write_tree(self.collab, UNTESTED_MARKER)
        git(self.collab, "commit", "-am", "shift C")
        git(self.collab, "push", "origin", self.branch)
        untested = rev_parse(self.collab, "HEAD")
        assert untested is not None
        return untested

    @staticmethod
    def _write_tree(repo: Path, marker: str) -> None:
        (repo / "composer.json").write_text(
            '{\n  "name": "example/app",\n  "version": "' + marker + '"\n}\n'
        )
        (repo / "marker.txt").write_text(marker + "\n")


def expand_merge_message(shell: SkillShell, template: str, platform: str, branch: str) -> str:
    """Expand agent placeholders, then shell variables and command substitutions.

    Braces already written as ``${NAME}`` stay as that variable. Other
    ``{NAME}`` placeholders become shell variables. The message is expanded
    once by an unquoted here-document, with backticks escaped so a Markdown
    code span is not executed as a command.
    """
    rendered = template.replace("{platform}", platform)
    rendered = substitute_branch(rendered, branch)
    rendered = re.sub(r"(?<!\$)\{([A-Za-z_][A-Za-z0-9_]*)\}", r"${\1}", rendered)
    rendered = " ".join(rendered.splitlines())
    body = rendered.replace("\\", "\\\\").replace("`", "\\`")
    delimiter = "REVIEW_MERGE_EOF"
    while delimiter in body:
        delimiter += "_X"
    output_path = Path(shell._root) / f"merge-{platform}.out"
    script = (
        f"message=$(cat <<{delimiter}\n"
        f"{body}\n"
        f"{delimiter}\n"
        ")\n"
        "printf '%s\\n' \"$message\" > " + shlex.quote(str(output_path)) + "\n"
    )
    result = shell.run(script)
    if result.returncode != 0 or not output_path.exists():
        raise AssertionError(
            "Could not expand the GitLab/Bitbucket merge instruction.\n"
            f"{result.stdout}{result.stderr}"
        )
    return output_path.read_text().strip()


def run_gitlab_bitbucket_review(repo: Repository, skill: str, number: int) -> list[str]:
    """Execute the skill's GitLab/Bitbucket commands. Return every mismatch."""
    steps = split_steps(skill)
    for required in (2, 4, 6, 10):
        if required not in steps:
            return [f"Review skill is missing step {required}."]
    shell = SkillShell(repo.dev, str(number))
    errors: list[str] = []
    try:
        fetch_blocks = bash_fences(gitlab_bitbucket_section(steps[2]))
        if not fetch_blocks:
            return ["Step 2 has no GitLab/Bitbucket fetch commands."]
        fetch_output = ""
        branch = None
        for block in fetch_blocks:
            result = shell.run(block)
            # The skill runs the shift-build fetch only when the shift-<n> fetch fails.
            if result.returncode != 0:
                continue
            branch = tracking_branch(repo.dev, number)
            fetch_output = result.stdout + result.stderr
            if branch == repo.branch and rev_parse(repo.dev, f"origin/{branch}") == repo.reviewed:
                break
        if branch is None:
            branch = tracking_branch(repo.dev, number)
        if branch != repo.branch:
            return [
                f"After the step 2 fetch, origin/{repo.branch} was not available "
                f"(resolved {branch!r}).\n{fetch_output}"
            ]
        fetched = rev_parse(repo.dev, f"origin/{branch}")
        if fetched != repo.reviewed:
            return [
                "The fetch did not leave the remote-tracking ref at the commit "
                f"that was pushed before the review. Expected {repo.reviewed}, "
                f"got {fetched}."
            ]
        if REVIEWED_MARKER not in fetch_output:
            errors.append(
                "The step 2 diff did not show the fetched tip. "
                f"Output was:\n{fetch_output}"
            )
        untested = repo.push_untested_commit()
        if rev_parse(repo.dev, f"origin/{branch}") != repo.reviewed:
            return ["The remote-tracking ref moved before the skill checked it out."]
        remote_tip = git(
            repo.dev, "ls-remote", "origin", f"refs/heads/{branch}"
        ).stdout.split()[0]
        if remote_tip != untested:
            return [f"The untested commit was not on the remote ({remote_tip})."]

        for block in bash_fences(gitlab_bitbucket_section(steps[4])):
            result = shell.run(substitute_branch(block, branch))
            if result.returncode != 0:
                errors.append(
                    "Checkout commands exited "
                    f"{result.returncode}:\n{result.stdout}{result.stderr}"
                )
        for block in bash_fences(gitlab_bitbucket_section(steps[6])):
            shell.run(substitute_branch(block, branch))

        step10 = steps[10]
        git_commands = [
            substitute_branch(command, branch)
            for command in re.findall(r"`([^`\n]+)`", step10)
            if command.strip().startswith("git ")
        ]
        status_commands = [command for command in git_commands if "status" in command]
        log_commands = [command for command in git_commands if command.startswith("git log")]
        push_commands = [command for command in git_commands if command.startswith("git push")]
        if status_commands:
            status = shell.run(status_commands[0])
            if status.stdout.strip():
                errors.append(
                    "Step 10 saw uncommitted changes, so the merge instruction "
                    f"is not for a clean reviewed tree:\n{status.stdout}"
                )
        unpushed = ""
        if log_commands:
            logged = shell.run(log_commands[0])
            unpushed = logged.stdout.strip()
        if unpushed and push_commands:
            shell.run(push_commands[0])

        template = first_blockquote(gitlab_bitbucket_section(step10))
        head = rev_parse(repo.dev, "HEAD")
        worktree_marker = (repo.dev / "marker.txt").read_text().strip() if (repo.dev / "marker.txt").exists() else "<missing>"
        composer = (repo.dev / "composer.json").read_text() if (repo.dev / "composer.json").exists() else "<missing>"
        if head != repo.reviewed:
            errors.append(
                "The worktree HEAD is not the commit step 2 fetched and diffed. "
                f"HEAD={head}, reviewed={repo.reviewed}, previous local={repo.stale}, "
                f"later remote tip={untested}."
            )
        if worktree_marker != REVIEWED_MARKER or REVIEWED_MARKER not in composer:
            errors.append(
                "Composer and the test suite would see marker "
                f"{worktree_marker!r} and composer.json {composer!r}, not the "
                f"reviewed tree {REVIEWED_MARKER!r}."
            )
        if UNTESTED_MARKER in composer or worktree_marker == UNTESTED_MARKER:
            errors.append("The worktree contains the commit pushed after the diff.")
        if worktree_marker == STALE_MARKER:
            errors.append("The worktree is still the local branch's previous commit.")
        for platform in ("GitLab", "Bitbucket"):
            message = expand_merge_message(shell, template, platform, branch)
            if repo.reviewed not in message:
                errors.append(
                    f"The {platform} merge instruction does not name the reviewed "
                    f"commit {repo.reviewed}:\n{message}"
                )
            if untested in message or (repo.stale and repo.stale in message):
                errors.append(
                    f"The {platform} merge instruction names a commit that was not "
                    f"the reviewed tree:\n{message}"
                )
            if platform not in message:
                errors.append(
                    f"The {platform} merge instruction does not address {platform}:\n{message}"
                )
            if "merge" not in message.lower():
                errors.append(f"The {platform} instruction does not ask the developer to merge.")
    finally:
        shell.close()
    return errors


class ReviewSkillCheckoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if shutil.which("git") is None or shutil.which("bash") is None:
            raise unittest.SkipTest("git and bash are required")
        cls.skill = SKILL_PATH.read_text()

    def test_second_review_of_shift_branch_uses_fetched_commit(self) -> None:
        self._check("shift", 17, local_branch=True)

    def test_second_review_of_shift_build_branch_uses_fetched_commit(self) -> None:
        self._check("shift-build", 17, local_branch=True)

    def test_first_review_merge_instruction_names_fetched_commit(self) -> None:
        self._check("shift", 18, local_branch=False)

    def test_merge_message_keeps_braced_variables_and_markdown_backticks(self) -> None:
        root = tempfile.TemporaryDirectory(prefix="review-merge-msg-")
        shell = SkillShell(Path(root.name), "1")
        try:
            sha = "0123456789abcdef0123456789abcdef01234567"
            shell.env["REVIEWED_COMMIT"] = sha
            braced = expand_merge_message(
                shell,
                "Merge ${REVIEWED_COMMIT} on {platform}.",
                "GitLab",
                "shift-19",
            )
            self.assertEqual(braced, f"Merge {sha} on GitLab.")
            quoted = expand_merge_message(
                shell,
                "Merge `{REVIEWED_COMMIT}` on {platform}.",
                "Bitbucket",
                "shift-19",
            )
            self.assertEqual(quoted, f"Merge `{sha}` on Bitbucket.")
            command = expand_merge_message(
                shell,
                "Merge $(printf '%s' ok) {REVIEWED_COMMIT} on {platform}.",
                "GitLab",
                "shift-19",
            )
            self.assertEqual(command, f"Merge ok {sha} on GitLab.")
        finally:
            shell.close()
            root.cleanup()

    def _check(self, prefix: str, number: int, local_branch: bool) -> None:
        repo = Repository(f"{prefix}-{number}")
        try:
            if not local_branch:
                repo.remove_local_branch()
            errors = run_gitlab_bitbucket_review(repo, self.skill, number)
        finally:
            repo.close()
        if errors:
            self.fail("\n".join(errors))


if __name__ == "__main__":
    unittest.main()
