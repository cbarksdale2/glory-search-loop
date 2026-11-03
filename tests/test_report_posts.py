"""Guard (report bug 2026-11-02): a post published after the last collect still shows in the weekly report."""
from helpers import StateCase
from loop import watchdog, core


class ReportPosts(StateCase):
    def test_ledger_post_shows_before_next_collect(self):
        core.ledger_add({"action": "publish", "slug": "why-x", "url": "https://glorybyus.com/blogs/the-process/why-x",
                         "article_id": "a1", "undo": {"op": "unpublish", "article_id": "a1"}})
        lines = watchdog.post_lines({"articles": []})
        self.assertEqual(len(lines), 1)
        self.assertIn("/blogs/the-process/why-x", lines[0])
