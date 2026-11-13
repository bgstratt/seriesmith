"""tools/release_notes.py: a release's RELEASES.md entry as the Registry's one paragraph."""
import os
import sys
import tomllib
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import release_notes  # noqa: E402

RELEASES = """- [x] **0.1.21** (2026-11-09, `release-0.1.21`): the skill's zip under 200
      files (#113). Published by the merge's version bump.
- [x] **0.1.22** (2026-11-10, `release-0.1.22`): the Registry's flags answered (#115: the
      package trimmed, `python -c` gone); continuity from the out point (#116). Published by
      the merge's version bump.
- [ ] **Live:** not a release.
"""


class NotesTest(unittest.TestCase):
    def test_an_entry_is_one_paragraph(self):
        raw = release_notes.entry(RELEASES, "0.1.22")
        self.assertEqual(
            release_notes.notes(raw),
            "The Registry's flags answered (the package trimmed, python -c gone); "
            "continuity from the out point.")

    def test_only_its_own_lines(self):
        self.assertEqual(release_notes.notes(release_notes.entry(RELEASES, "0.1.21")),
                         "The skill's zip under 200 files.")

    def test_no_entry(self):
        self.assertIsNone(release_notes.entry(RELEASES, "0.1.2"))

    def test_this_version_has_notes(self):
        """A release bumps pyproject.toml and writes its RELEASES.md entry together: the publish
        workflow sends that entry as the version's notes, and fails without one."""
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as f:
            version = tomllib.load(f)["project"]["version"]
        with open(release_notes.RELEASES, encoding="utf-8") as f:
            raw = release_notes.entry(f.read(), version)
        self.assertIsNotNone(raw, f"docs/RELEASES.md has no entry for {version}")
        self.assertTrue(release_notes.notes(raw))


if __name__ == "__main__":
    unittest.main()
