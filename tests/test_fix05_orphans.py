"""Fix 5: no orphan posts: a new post must link 3 live posts, and every live post gets linked back."""
from helpers import StateCase
import fakes
from loop import gate, publish, core


class Fix05Orphans(StateCase):
    def test_links_required_and_older_posts_updated(self):
        lives = [{"id": f"gid://shopify/Article/{i}", "slug": f"p{i}", "title": f"Post {i}", "url": f"https://glorybyus.com/blogs/the-process/p{i}",
                  "text": "", "body": "<p>old</p>", "publishedAt": "2026-10-01"} for i in range(1, 5)]
        probs = gate.check(fakes.good(), fakes.FACTS, lives, fetch=lambda u: (404, ""))
        self.assertTrue(any("links 0 other posts (needs 3)" in p for p in probs))
        shop = fakes.FakeShop()
        n = publish.refresh_related(shop, lives)
        self.assertEqual(n, 4)
        body = shop.mutations("articleUpdate")[0]["a"]["body"]
        self.assertIn("More from The Process", body)
        self.assertEqual(body.count("/blogs/the-process/p"), 3)
        self.assertTrue(all(e["undo"]["op"] == "restore_body" for e in core.ledger()))
