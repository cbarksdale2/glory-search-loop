"""Fix 8: without a complete, current Claude polish the week is skipped; a free-model-only draft is never published."""
import os, time
from helpers import StateCase
import fakes
from loop import publish, core


class Fix08PolishMissing(StateCase):
    def test_missing_incomplete_or_stale_polish_skips(self):
        slug = "why-is-pomade-paste-good-for-beards"
        core.write_json(core.spath("picks", f"{core.iso_week()}.json"), {"pick": {"slug": slug, "title": "t", "products": ["pomade-paste"]}})
        core.write_json(core.spath("facts.json"), fakes.FACTS)
        open(core.spath("drafts", f"{slug}.draft.md"), "w").write(fakes.GOOD)
        shop = fakes.FakeShop()
        for content in (None, fakes.GOOD):  # missing, then present but with no completion line
            if content:
                open(core.spath("drafts", f"{slug}.polished.md"), "w").write(content)
            with self.assertRaises(core.NamedStop) as c:
                publish.run(gql=shop, verify=False)
            self.assertEqual(c.exception.code, "POLISH_MISSING")
        p = core.spath("drafts", f"{slug}.polished.md")
        open(p, "w").write(fakes.GOOD + "\nPOLISH-COMPLETE")
        old = time.time() - 3600
        os.utime(p, (old, old))  # polish older than the draft
        with self.assertRaises(core.NamedStop) as c:
            publish.run(gql=shop, verify=False)
        self.assertEqual(c.exception.code, "POLISH_MISSING")
        self.assertEqual(shop.mutations("articleCreate"), [])
