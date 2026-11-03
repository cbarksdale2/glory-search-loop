import os, sys, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class StateCase(unittest.TestCase):
    """Each test gets an empty state dir and a pinned home clock (Mon 2 Nov 2026, 10:00 ET)."""
    NOW = "2026-11-02T10:00:00-05:00"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._env = dict(os.environ)
        os.environ["LOOP_STATE"] = self.tmp.name
        os.environ["LOOP_NOW"] = self.NOW
        for k in list(os.environ):
            if k.endswith("_GLORY") or k.endswith("_GLORY_BLOG") or k in ("LOOP_PAUSED", "GITHUB_TOKEN"):
                del os.environ[k]

    def tearDown(self):
        os.environ.clear(); os.environ.update(self._env)
        self.tmp.cleanup()
