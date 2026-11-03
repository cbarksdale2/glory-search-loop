"""Fix 9: no weekly report for more than 8 days means the loop is down (red issue)."""
from helpers import StateCase
from loop import watchdog, core


class Fix09Heartbeat(StateCase):
    def test_stale_report_is_down_fresh_is_up(self):
        down, _ = watchdog.heartbeat(post=False, started="2026-10-20T09:00:00-05:00")   # no report, loop 13 days old
        self.assertTrue(down)
        down, _ = watchdog.heartbeat(post=False, started="2026-11-01T09:00:00-05:00")   # brand new loop
        self.assertFalse(down)
        core.write_json(core.spath("reports", "2026-W43.json"), {"at": "2026-10-24T09:30:00-04:00"})
        down, age = watchdog.heartbeat(post=False)
        self.assertTrue(down); self.assertGreater(age, 8)
        core.write_json(core.spath("reports", "2026-W45.json"), {"at": "2026-11-02T09:30:00-05:00"})
        self.assertFalse(watchdog.heartbeat(post=False)[0])
