"""Fix 11: heal turns findings into actions: re-ping, strengthen, merge; foundational posts are never merged away."""
import datetime as dt
from helpers import StateCase
from loop import heal


def collect(url, imp, verdict):
    return {"gsc": {"current": {"pages": [{"keys": [url], "impressions": imp, "clicks": 0}]}},
            "index_status": {url.replace("https://glorybyus.com", ""): {"verdict": verdict}}}


class Fix11Remedies(StateCase):
    def test_actions_by_milestone(self):
        today = dt.date(2026, 12, 28)
        u = "https://glorybyus.com/blogs/the-process/x"
        p = {"slug": "x", "url": u, "published": "2026-11-02", "article_id": "a"}
        ops = {a["key"]: a["op"] for a in heal.post_actions([p], collect(u, 0, "NEUTRAL"), set(), today, set())}
        self.assertEqual(ops["x-2w"], "reping")
        self.assertEqual(ops["x-4w"], "strengthen")
        self.assertEqual(ops["x-8w"], "merge")
        ops = {a["key"]: a["op"] for a in heal.post_actions([p], collect(u, 0, "PASS"), {"x"}, today, set())}
        self.assertEqual(ops["x-8w"], "strengthen")  # foundational: strengthened, never merged
        self.assertEqual(heal.post_actions([p], collect(u, 0, "PASS"), set(), today, {"x-2w", "x-4w", "x-8w"}), [])
        notread = heal.post_actions([p], {"gsc": {"not_read": "x"}}, set(), today, set())
        self.assertTrue(all(a["op"] == "note" for a in notread))
