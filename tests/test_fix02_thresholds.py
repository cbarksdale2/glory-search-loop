"""Fix 2: small numbers never alert; a real drop on a meaningful base does."""
from helpers import StateCase
from loop import watchdog, core


def collect(cur, prior):
    return {"gsc": {"current": {"totals": cur, "pages": [], "queries": []},
                    "prior": {"totals": prior, "pages": [], "queries": []}}}


class Fix02Thresholds(StateCase):
    def test_small_base_is_quiet_and_big_base_alerts(self):
        thr = core.config("site.json")["thresholds"]
        quiet, _ = watchdog.analyse(collect({"clicks": 0, "impressions": 5}, {"clicks": 4, "impressions": 40}), thr, [])
        self.assertEqual(quiet, [])
        loud, _ = watchdog.analyse(collect({"clicks": 3, "impressions": 60}, {"clicks": 20, "impressions": 200}), thr, [])
        self.assertEqual(len(loud), 1)
        missing, notes = watchdog.analyse({"gsc": {"not_read": "HTTP 500"}}, thr, [])
        self.assertEqual(missing, []); self.assertIn("not read", notes[0])
