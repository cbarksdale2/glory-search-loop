"""Fix 6: IndexNow is only pinged when the key file really serves the key; otherwise a named stop and the sitemap carries discovery."""
from helpers import StateCase
from loop import clients


class Fix06IndexNow(StateCase):
    def test_keyfile_must_serve_the_key(self):
        key = clients.indexnow_key()
        self.assertIsNone(clients.indexnow_check_keyfile(fetch=lambda u: (200, key + "\n")))
        stop = clients.indexnow_check_keyfile(fetch=lambda u: (200, "<html>404 Not Found</html>"))
        self.assertEqual(stop.code, "INDEXNOW_KEYFILE")
        self.assertEqual(clients.indexnow_check_keyfile(fetch=lambda u: (404, "")).code, "INDEXNOW_KEYFILE")
