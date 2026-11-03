"""Credential pre-checks: each owner-held credential is tried read-only; a failure is a named stop
with the one step only the owner can take. Optional ones (Clarity, Bing) report 'not set up'."""
import json
import os

from . import clients
from .core import NamedStop, http

OPTIONAL = {
    "CLARITY_EXPORT_TOKEN_GLORY": "Clarity AI-referral numbers stay 'not read'. Owner: Shopify admin > Apps > Microsoft Clarity > "
                                  "Settings > Data export > Generate new API token, then save it as this Actions secret.",
    "BING_WEBMASTER_API_KEY_GLORY": "Bing numbers stay 'not read'. Owner: Bing Webmaster Tools > Settings > API access > "
                                    "API key > Generate, then save it as this Actions secret.",
}


def check_shopify():
    clients.gql("{ shop { name } }")


def check_gsc():
    sites = [s["siteUrl"] for s in clients.gsc("https://www.googleapis.com/webmasters/v3/sites").get("siteEntry", [])]
    if clients.GSC_SITE not in sites:
        raise NamedStop("GSC_PROPERTY_MISSING", "the signed-in Google account no longer sees https://glorybyus.com/ in Search Console. "
                        "Owner: re-add the account as a user of the property.", 3)


def check_openrouter():
    key = os.environ.get("OPENROUTER_API_KEY_GLORY_BLOG", "").strip()
    if not key:
        raise NamedStop("MISSING_OPENROUTER_API_KEY_GLORY_BLOG", "Owner: save the $0-limit OpenRouter key as the Actions secret.", 3)
    st, body = http("https://openrouter.ai/api/v1/key", headers={"Authorization": "Bearer " + key})
    if st != 200:
        raise NamedStop("OPENROUTER_KEY_REFUSED", f"OpenRouter refused the key (HTTP {st}). Owner: create a new $0-limit key.", 3)
    d = json.loads(body).get("data", {})
    if d.get("limit") not in (0, 0.0) and not d.get("is_free_tier"):
        raise NamedStop("OPENROUTER_KEY_CAN_SPEND", "the OpenRouter key has a spending limit above $0; drafting is paused. "
                        "Owner: set the key's limit to $0.", 3)


REQUIRED = [("shopify", check_shopify), ("search console", check_gsc), ("openrouter", check_openrouter)]


def run_all(required=None):
    """Returns (stops, notes). stops: list of NamedStop for required credentials; notes: optional ones missing."""
    stops, notes = [], []
    for name, fn in (required or REQUIRED):
        try:
            fn()
        except NamedStop as e:
            stops.append(e)
    for var, why in OPTIONAL.items():
        if not os.environ.get(var, "").strip():
            notes.append(f"{var} not set: {why}")
    ki = None
    try:
        ki = clients.indexnow_check_keyfile()
    except NamedStop as e:
        ki = e
    if ki:
        stops.append(ki)
    return stops, notes
