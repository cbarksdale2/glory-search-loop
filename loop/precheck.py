"""Credential pre-checks: each owner-held credential is tried read-only; a failure is a named stop
with the one step only the owner can take. Optional ones (Clarity, Bing) report 'not set up'."""
import json
import os
import urllib.parse

from . import clients
from .core import NamedStop, http

OPTIONAL = {
    "CLARITY_EXPORT_TOKEN_GLORY": "Connect Clarity so the report can count visitors sent by ChatGPT, Perplexity and Copilot: "
                                  "Shopify admin > Apps > Microsoft Clarity > Settings > Data export > Generate new API token, then hand it to Claude to save.",
    "BING_WEBMASTER_API_KEY_GLORY": "Connect Bing so the report can show Bing searches: Bing Webmaster Tools > Settings > API access > "
                                    "Generate API key, then hand it to Claude to save.",
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
            notes.append(why)
    try:
        sm = clients.gsc(f"https://www.googleapis.com/webmasters/v3/sites/{urllib.parse.quote(clients.GSC_SITE, safe='')}/sitemaps")
        if not any(s.get("path", "").endswith("/sitemap.xml") for s in sm.get("sitemap", [])):
            notes.append("Submit the sitemap in Google Search Console so new posts are found faster: Search Console > Sitemaps > "
                         "type sitemap.xml > Submit (the loop's Google access is read-only, so it cannot do this itself).")
    except NamedStop:
        pass  # a Search Console outage is already a required-credential stop above
    ki = None
    try:
        ki = clients.indexnow_check_keyfile()
    except NamedStop as e:
        ki = e
    if ki:
        stops.append(ki)
    return stops, notes
