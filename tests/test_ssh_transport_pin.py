"""Pinned remote commands stay usable on Git for Windows and still authenticate gh.

Run from the repository root:

    python3 -m unittest tests.test_ssh_transport_pin -v
"""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class SshTransportPinTest(unittest.TestCase):
    def test_fixed_path_includes_git_for_windows(self) -> None:
        for name in ("review", "run", "refactor"):
            text = (ROOT / "skills" / name / "SKILL.md").read_text()
            self.assertIn("/mingw64/bin", text, name)

    def test_gh_remote_commands_keep_home_and_tokens(self) -> None:
        text = (ROOT / "skills" / "review" / "SKILL.md").read_text()
        self.assertGreaterEqual(text.count('HOME="$shift_home"'), 2)
        self.assertGreaterEqual(text.count('GH_TOKEN="$GH_TOKEN"'), 2)
        checkout = text.find('"$shift_gh" pr checkout')
        merge = text.find('"$shift_gh" pr merge')
        self.assertGreater(checkout, text.find('HOME="$shift_home"'))
        self.assertGreater(merge, text.rfind('HOME="$shift_home"'))


if __name__ == "__main__":
    unittest.main()
