"""Fix 7: a missing owner credential is a named stop with exit 3, not a crash or a silent skip."""
from helpers import StateCase
from loop import precheck, clients


class Fix07Precheck(StateCase):
    def test_missing_credentials_become_owner_stops(self):
        clients._tokens.clear()
        ok_keyfile = lambda: None
        orig = clients.indexnow_check_keyfile
        clients.indexnow_check_keyfile = ok_keyfile
        try:
            stops, notes = precheck.run_all([("shopify", precheck.check_shopify), ("openrouter", precheck.check_openrouter)])
        finally:
            clients.indexnow_check_keyfile = orig
        self.assertEqual(len(stops), 2)
        self.assertTrue(all(s.exit_code == 3 for s in stops))
        self.assertTrue(any("SHOPIFY_CLIENT_ID_GLORY" in str(s) for s in stops))
        self.assertEqual(len(notes), 2)  # Clarity and Bing not set up are named
