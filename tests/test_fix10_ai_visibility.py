"""Fix 10: AI referrals without a Clarity token are 'not read', never 0."""
import json
from helpers import StateCase
from loop import watchdog


class Fix10AiVisibility(StateCase):
    def test_no_token_is_not_read_and_token_counts(self):
        r = watchdog.ai_referrals(token="")
        self.assertIn("not_read", r)
        self.assertNotIn("last_3_days", r)
        body = json.dumps([{"metricName": "Traffic", "information": [{"ReferrerUrl": "https://chatgpt.com/", "totalSessionCount": "4"}]}])
        r = watchdog.ai_referrals(token="t", fetch=lambda: (200, body))
        self.assertEqual(r["last_3_days"]["chatgpt.com"], 4)
        subject, text, red = watchdog.build_report(None, {}, [], [], [], [], watchdog.ai_referrals(token=""), [])
        self.assertIn("not read", text)
