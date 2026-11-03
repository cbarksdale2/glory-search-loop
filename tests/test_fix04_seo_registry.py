"""Fix 4: approved SEO values are put back when the live site drifts (with undo); homepage drift is an owner step."""
from helpers import StateCase
import fakes
from loop import heal, core


def page(title, desc):
    return 200, f'<title>{title} &ndash; Glory By Us</title><meta name="description" content="{desc}">'


class Fix04SeoRegistry(StateCase):
    def test_drift_is_reapplied_and_homepage_is_owner_step(self):
        reg = core.config("seo_registry.json")
        live = {d["path"]: page("X", d["description"]) for d in reg["descriptions"]}
        live["/"] = page(reg["homepage"]["title"], reg["homepage"]["description"])
        fetch = lambda u: live[u.replace(core.SITE, "")]
        self.assertEqual(heal.drift(reg, fetch)[:2], ([], []))
        live["/pages/contact"] = page("Contact", "Something else")
        live["/"] = page("GLORY BY US", "old text")
        shop = fakes.FakeShop()
        done, owner, unread = heal.reapply_seo(gql=shop, fetch=fetch)
        self.assertEqual(len(done), 1); self.assertEqual(len(owner), 1)
        self.assertEqual(len(shop.mutations("pageUpdate")), 1)
        e = core.ledger()[-1]
        self.assertEqual(e["undo"]["old"], "Something else")
