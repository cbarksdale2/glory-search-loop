"""Fix 1: every job ends in a sentinel; a job that did nothing is NOT RUN, never 'ok'."""
from helpers import StateCase
from loop import tick, core


class Fix01Sentinel(StateCase):
    def test_job_that_did_nothing_is_a_stop_and_missing_is_not_run(self):
        self.assertEqual(core.sentinel_state("collect", 1.5)[0], "NOT RUN")      # never ran -> NOT RUN
        status, _ = tick.run_job("collect", lambda: "")                          # did nothing
        self.assertEqual(status, "NOTHING_DONE")
        self.assertTrue(core.sentinel_state("collect", 1.5)[0].startswith("STOPPED"))
        status, _ = tick.run_job("collect", lambda: "collected 5/5 sources")
        self.assertEqual(status, "ok")
        self.assertEqual(core.sentinel_state("collect", 1.5)[0], "ran")
