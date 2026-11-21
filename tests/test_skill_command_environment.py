"""The scrubbed skill commands have to run on macOS and refuse a late push.

Run from the repository root:

    python3 -m unittest tests.test_skill_command_environment -v
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("review", "run", "refactor")


class SkillCommandEnvironmentTest(unittest.TestCase):
    def test_home_lookup_falls_back_to_directory_services(self) -> None:
        for name in SKILLS:
            text = (ROOT / "skills" / name / "SKILL.md").read_text()
            dscl = text.find("NFSHomeDirectory")
            failure = text.find("could not resolve the passwd home")
            self.assertGreater(dscl, 0, name)
            self.assertGreater(failure, dscl, name)
            self.assertIn('command -v dscl', text)

    def test_shift_branch_is_checked_before_the_push(self) -> None:
        text = (ROOT / "skills" / "review" / "SKILL.md").read_text()
        confirm = text.find("first confirm `git branch --show-current`")
        push = text.find('push --no-follow-tags --recurse-submodules=no origin "HEAD:$ref"')
        self.assertGreater(confirm, 0)
        self.assertGreater(push, confirm)
        self.assertLess(
            text.find("HEAD is not the Shift branch; not pushing"),
            push,
        )


if __name__ == "__main__":
    unittest.main()
