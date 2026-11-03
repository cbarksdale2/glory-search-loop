"""Fix 3: gate + kill switch + 1/week cap + undo ledger."""
import os
from helpers import StateCase
import fakes
from loop import gate, publish, rollback, core


def ready(slug="why-is-pomade-paste-good-for-beards"):
    core.write_json(core.spath("picks", f"{core.iso_week()}.json"), {"pick": {"slug": slug, "title": "Why is Pomade Paste good for beards?", "products": ["pomade-paste"]}})
    core.write_json(core.spath("facts.json"), fakes.FACTS)
    open(core.spath("drafts", f"{slug}.polished.md"), "w").write(fakes.GOOD + "\nPOLISH-COMPLETE\n")


class Fix03Gate(StateCase):
    def test_gate_blocks_claims_pause_blocks_cap_blocks_and_undo_works(self):
        self.assertEqual(gate.check(fakes.good(), fakes.FACTS, [], fetch=lambda u: (404, "")), [])
        bad = fakes.GOOD.replace("lays the beard down", "regrows thin patches and stops hair loss while it lays the beard down")
        probs = gate.check(fakes.good().__class__(publish.postmod.parse(bad)), fakes.FACTS, [], fetch=lambda u: (404, ""))
        self.assertTrue(any("claim word" in p for p in probs))
        self.assertTrue(any("argan" in p for p in gate.check(publish.postmod.parse(fakes.GOOD.replace("shea butter,", "argan oil,")), fakes.FACTS, [], fetch=lambda u: (404, ""))))

        ready(); shop = fakes.FakeShop()
        os.environ["LOOP_PAUSED"] = "true"
        with self.assertRaises(core.NamedStop) as c:
            publish.run(gql=shop, verify=False)
        self.assertEqual(c.exception.code, "PAUSED"); self.assertEqual(shop.mutations("articleCreate"), [])
        del os.environ["LOOP_PAUSED"]

        line = publish.run(gql=shop, verify=False)
        self.assertIn("published", line)
        e = [x for x in core.ledger() if x["action"] == "publish"][0]
        self.assertEqual(e["undo"]["op"], "unpublish")
        with self.assertRaises(core.NamedStop) as c:
            publish.run(gql=shop, verify=False)
        self.assertEqual(c.exception.code, "WEEKLY_CAP"); self.assertEqual(len(shop.mutations("articleCreate")), 1)

        rollback.rollback("last", gql=shop)
        self.assertEqual(shop.mutations("articleUpdate")[-1], {"id": e["article_id"]})
