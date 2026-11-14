"""
The generated documentation stays in step with the code.

  - INSTALL.md's model list is what tools/make_models_md.py emits today, so a
    target that gains, loses or renames a model file cannot leave the install
    instructions pointing at the old one (`python tools/make_models_md.py`).
  - The generated block is honest: every file it lists is one some target
    names, with the folder and tier that target gives it, and a URL only where
    target.json records one.
  - prompts/ is what tools/make_prompts.py emits from docs/AUTHORING.md today,
    so an edit to the authoring guide cannot leave the script-writing skill
    describing the old format (`python tools/make_prompts.py`). The committed
    copies are the skill's text (SKILL.md) and the same guide as assistant
    instructions; build/skill/ is gitignored and rebuilt from the same source.
  - docs/site/ (the Mintlify site, docs.seriesmith.com) is what
    tools/make_site_docs.py emits from INSTALL.md and the user docs today, and
    names no internal document (`python tools/make_site_docs.py`); every page,
    the hand-written tutorials too, is in its navigation.
  - seriesmith/core/structures.json (the first-pass score's Music tables) is
    what tools/make_structures.py reads from docs/STORY_STRUCTURES.md today
    (`python tools/make_structures.py`).
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_models_md as M  # noqa: E402
import make_prompts as P  # noqa: E402
import make_site_docs as S  # noqa: E402
from seriesmith import targets as TG  # noqa: E402


class TestScriptSkill(unittest.TestCase):
    """The skill and the assistant instructions are docs/AUTHORING.md."""

    def generated(self) -> dict:
        """What `python tools/make_prompts.py --no-bundle` would write now."""
        return {
            "prompts/SKILL.md": P.skill_text(P.body()),
            "prompts/" + P.INSTRUCTIONS: P.instructions_text(),
            **{f"prompts/references/{name}": text for name, text in P.references().items()},
        }

    def test_no_reference_left_behind(self):
        """prompts/references/ holds the references the generator writes and no other."""
        folder = os.path.join(ROOT, "prompts", "references")
        self.assertEqual(sorted(os.listdir(folder)), sorted(P.references()))

    def test_up_to_date(self):
        for rel, want in self.generated().items():
            with self.subTest(file=rel):
                path = os.path.join(ROOT, *rel.split("/"))
                self.assertTrue(os.path.isfile(path), path)
                with open(path, encoding="utf-8") as fh:
                    got = fh.read()
                self.assertEqual(
                    got.replace("\r\n", "\n"), want.replace("\r\n", "\n"),
                    f"{rel} is out of date -- run `python tools/make_prompts.py` "
                    f"and commit the result")

    def test_zip_up_to_date(self):
        """The committed skill zip (what a user installs) says what the guide says. Only its
        text: the build it bundles is refreshed before a release, not on every change."""
        import zipfile
        path = os.path.join(ROOT, "prompts", P.NAME + ".zip")
        self.assertTrue(os.path.isfile(path), path)
        text = P.body()
        with zipfile.ZipFile(path) as zf:
            for arc, want in ((f"{P.NAME}/SKILL.md", P.bundle_skill(text)),
                              *((f"{P.NAME}/references/{name}", ref) for name, ref in P.references().items())):
                with self.subTest(file=arc):
                    self.assertEqual(zf.read(arc).decode("utf-8"), want,
                                     f"prompts/{P.NAME}.zip is out of date -- run "
                                     "`python tools/make_prompts.py` and commit the result")

    def test_no_links_into_the_repo(self):
        """The skill is read away from the repo: a relative link to a doc, or AUTHORING by
        name, points at nothing there."""
        import re
        text = P.body()
        for name, got in (("SKILL.md", P.bundle_skill(text)), *P.references().items()):
            with self.subTest(file=name):
                self.assertEqual(re.findall(r"\]\((?!https?:|#)[^)]*\)", got), [])
                self.assertNotIn("AUTHORING", got)
                # no document of the repo by its file's name: its reader can't open one
                self.assertEqual(re.findall(r"\b[A-Z][A-Z_]+\.md\b", got.replace("SKILL.md", "")), [])

    def test_the_one_file_instructions_name_no_file_they_lack(self):
        """They are one file: no reference to read, no bundled check to run."""
        text = P.instructions_text()
        self.assertNotIn("references/", text)
        self.assertNotIn("scripts/check.py", text)
        self.assertIn("## Starting a series: what to settle first", text)


class TestSkillSplit(unittest.TestCase):
    """AUTHORING.md's `skill:ref` and `skill:omit` markers (docs/SKILL_SPLIT.md): what the
    generator makes of them, on a document of its own and on the real one."""

    DOC = ("## One\n\ncore one\n\n<!-- skill:ref models -->\n### A model\n\nmodel words\n<!-- /skill:ref -->\n\n"
           "## Two\n\n<!-- skill:omit -->\nfor a person\n<!-- /skill:omit -->\ncore two\n\n"
           "<!-- skill:ref models -->\n### Another\n\nmore\n<!-- /skill:ref -->\n\n```\n## sh010\n```\n")

    def test_the_core_the_references_and_the_whole(self):
        core, refs, whole = P.split(self.DOC)
        self.assertIn("core one", core)
        self.assertIn("core two", core)
        self.assertNotIn("model words", core)
        self.assertNotIn("for a person", core)
        self.assertNotIn("for a person", whole)
        self.assertNotIn("skill:", core + whole)
        # one trigger, where the first block was, naming the headings of both
        self.assertEqual(core.count("references/models.md"), 1)
        self.assertLess(core.index("references/models.md"), core.index("## Two"))
        self.assertIn("**A model**, **Another**", core)
        self.assertEqual(refs["models"], ["### A model\n\nmodel words", "### Another\n\nmore"])
        # the whole: every block where it was, in the document's order
        self.assertLess(whole.index("model words"), whole.index("core two"))
        self.assertLess(whole.index("core two"), whole.index("### Another"))

    def test_a_marker_that_is_wrong_fails(self):
        for bad in ("<!-- skill:ref models -->\nx\n",                                       # never closed
                    "<!-- skill:ref nowhere -->\nx\n<!-- /skill:ref -->\n",                 # no such reference
                    "<!-- skill:omit -->\n<!-- skill:ref models -->\n<!-- /skill:ref -->\n<!-- /skill:omit -->\n",
                    "<!-- /skill:ref -->\n",
                    "<!-- BEGIN PICTURES (generated) -->\n<!-- skill:omit -->\n<!-- /skill:omit -->\n<!-- END PICTURES -->\n",
                    "<!-- skill:reff models -->\n"):
            with self.subTest(doc=bad[:40]):
                with self.assertRaises(SystemExit):
                    P.split(bad)

    def test_every_block_lands_once(self):
        """Each marked block of AUTHORING.md is in exactly one reference and in the one-file
        instructions, and not in the core; SKILL.md names each reference it has once."""
        core, refs, whole = P.split(P.source())
        written = P.references()
        for name, blocks in refs.items():
            for block in blocks:
                first = next(ln for ln in block.split("\n") if ln.strip())
                with self.subTest(reference=name, block=first[:50]):
                    self.assertIn(block, written[f"{name}.md"])
                    self.assertIn(block, whole)
                    self.assertNotIn(block, core)
                    self.assertEqual([n for n, text in written.items() if block in text], [f"{name}.md"])
        skill = P.bundle_skill(core)
        for name in written:
            with self.subTest(named=name):
                self.assertEqual(skill.count(f"- `references/{name}`"), 1)
        for name, blocks in refs.items():
            if blocks:
                self.assertEqual(core.count(f"**Read `references/{name}.md`**"), 1, name)

    def test_the_core_stays_short(self):
        """SKILL.md is read whole each time the skill loads; what grows goes to a reference."""
        self.assertLessEqual(P.words(P.body()), P.MAX_CORE_WORDS)

    def test_the_site_page_has_no_marker(self):
        with open(os.path.join(S.SITE, "authoring.mdx"), encoding="utf-8") as fh:
            self.assertNotIn("skill:", fh.read())


class TestSiteDocs(unittest.TestCase):
    """The docs site's pages are the user docs."""

    def test_up_to_date(self):
        for src, name, desc in S.PAGES:
            with self.subTest(page=name):
                path = os.path.join(S.SITE, name + ".mdx")
                self.assertTrue(os.path.isfile(path), path)
                with open(path, encoding="utf-8") as fh:
                    got = fh.read().replace("\r\n", "\n")
                self.assertEqual(got, S.page(src, desc),
                                 f"docs/site/{name}.mdx is out of date -- run "
                                 "`python tools/make_site_docs.py` and commit the result")

    def test_every_page_is_in_the_navigation(self):
        import json
        with open(os.path.join(S.SITE, "docs.json"), encoding="utf-8") as fh:
            nav = [p for g in json.load(fh)["navigation"]["groups"] for p in g["pages"]]
        self.assertEqual(sorted(nav), sorted(S.hand_pages() + [name for _, name, _ in S.PAGES]))

    def test_last_light_quotes_the_demo(self):
        """Every titled code block on last-light.mdx (```json series.json) is lines of that
        file in examples/demo/, in order, so the page can't drift from the demo."""
        import re
        demo = os.path.join(ROOT, "examples", "demo")
        with open(os.path.join(S.SITE, "last-light.mdx"), encoding="utf-8") as fh:
            page = fh.read()
        blocks = re.findall(r"^```\w+ (\S+)\n(.*?)^```", page, re.M | re.S)
        self.assertGreater(len(blocks), 5)
        for name, body in blocks:
            with self.subTest(file=name, first=body.splitlines()[0][:60]):
                with open(os.path.join(demo, name), encoding="utf-8") as fh:
                    have = [ln.rstrip() for ln in fh.read().splitlines()]
                want = [ln.rstrip() for ln in body.splitlines()]
                self.assertTrue(any(have[i:i + len(want)] == want for i in range(len(have))),
                                f"last-light.mdx quotes {name} as it no longer is")

    def test_no_internal_document(self):
        sources = {src for src, _, _ in S.PAGES}
        self.assertFalse(sources & {"docs/DESIGN.md", "docs/PLAN.md", "docs/RELEASES.md",
                                    "docs/DAILIES.md"})


class TestPicturesBlock(unittest.TestCase):
    """AUTHORING.md's table of what each model takes in pictures is what
    tools/make_refs_md.py emits from the targets today."""

    def test_up_to_date(self):
        import make_refs_md as RM
        with open(RM.AUTHORING, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn(RM.BEGIN, text)
        got = text[text.index(RM.BEGIN):text.index(RM.END) + len(RM.END)]
        self.assertEqual(got, RM.block(), "AUTHORING.md's pictures table is out of date: run "
                                          "`python tools/make_refs_md.py` and commit the result")
        self.assertIn("| `seedance_2_5` |", got)
        self.assertIn("| `minimax_h3_ref2va` |", got)


class TestStructures(unittest.TestCase):
    """seriesmith/core/structures.json is docs/STORY_STRUCTURES.md's Music tables."""

    def test_up_to_date(self):
        import make_structures as MS
        with open(MS.DOC, encoding="utf-8") as fh:
            want = MS.render(MS.build(fh.read()))
        with open(MS.OUT, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), want, "structures.json is out of date: run "
                                              "`python tools/make_structures.py` and commit the result")


class TestModelsBlock(unittest.TestCase):
    def setUp(self):
        with open(M.INSTALL, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_install_md_has_the_markers(self):
        self.assertIn(M.BEGIN, self.text)
        self.assertIn(M.END, self.text)
        self.assertLess(self.text.index(M.BEGIN), self.text.index(M.END))

    def test_up_to_date(self):
        """Regenerate and compare, the way `--check` does."""
        self.assertEqual(
            M.splice(self.text, M.block()), self.text,
            "INSTALL.md's model list is out of date — run "
            "`python tools/make_models_md.py` and commit the result")

    def test_every_named_file_is_listed(self):
        """Every model file any target names has a row, in its folder."""
        block = M.block()
        for t in TG.list_targets():
            models = t.models
            for name, param in t.named_files().items():
                if param not in models:
                    continue
                with self.subTest(target=t.id, file=name):
                    self.assertIn(f"`{name}`", block)

    def test_no_invented_urls(self):
        """A row's link is a URL some target.json records, and a file with no
        record says so instead."""
        recorded = set()
        for t in TG.list_targets():
            for rec in t.downloads.values():
                if rec.get("url"):
                    recorded.add(rec["url"])
        for r in M.collect():
            with self.subTest(file=r["file"]):
                if r["url"]:
                    self.assertIn(r["url"], recorded)
                else:
                    self.assertIn("**none recorded**", M.link(r))
                    self.assertTrue(r["source"])

    def test_minimum_set_is_the_default_targets(self):
        self.assertEqual(M.MINIMUM, (TG.DEFAULT_VIDEO_TARGET, TG.DEFAULT_IMAGE_TARGET))
        minimum = [r for r in M.collect()
                   if any(u["target"] in M.MINIMUM for u in r["uses"])]
        self.assertTrue(minimum)
        for r in minimum:
            with self.subTest(file=r["file"]):
                self.assertIn(r["tier"], TG.TIERS)
                # the minimum tables name only the two default targets, even
                # for a file others share (krea2's VAE is also Wan 2.2's)
                cell = M.targets_cell(r, M.MINIMUM)
                self.assertTrue(cell)
                named = {b.strip().split(" ")[0].strip("`") for b in cell.split(",")}
                self.assertTrue(named <= set(M.MINIMUM), cell)


if __name__ == "__main__":
    unittest.main()
