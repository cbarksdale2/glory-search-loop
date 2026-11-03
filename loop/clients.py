"""Thin clients: Shopify Admin GraphQL, Search Console, GitHub issues, OpenRouter, IndexNow."""
import json
import os
import urllib.parse

from .core import NamedStop, env, http, SITE

SHOP = "glorybyus.myshopify.com"
API_VER = "2026-10"
GSC_SITE = "https://glorybyus.com/"
_tokens = {}


# ---------- Shopify ----------
def shopify_token():
    if "shop" not in _tokens:
        cid = env("SHOPIFY_CLIENT_ID_GLORY", "Owner: re-copy the client ID of the 'glory-claude' app into the Actions secret.")
        sec = env("SHOPIFY_CLIENT_SECRET_GLORY", "Owner: re-copy the client secret of the 'glory-claude' app into the Actions secret.")
        st, body = http(f"https://{SHOP}/admin/oauth/access_token",
                        urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}),
                        {"Content-Type": "application/x-www-form-urlencoded"})
        if st != 200:
            raise NamedStop("SHOPIFY_TOKEN_REFUSED", f"Shopify refused the app sign-in (HTTP {st}). Owner: check the 'glory-claude' app is still installed.", 3)
        _tokens["shop"] = json.loads(body)["access_token"]
    return _tokens["shop"]


def gql(query, variables=None):
    st, body = http(f"https://{SHOP}/admin/api/{API_VER}/graphql.json", {"query": query, "variables": variables or {}},
                    {"X-Shopify-Access-Token": shopify_token()})
    if st != 200:
        raise NamedStop("SHOPIFY_API", f"Shopify answered HTTP {st}", 1)
    d = json.loads(body)
    if d.get("errors"):
        raise NamedStop("SHOPIFY_API", f"Shopify errors: {str(d['errors'])[:300]}", 1)
    return d["data"]


def user_errors(payload):
    errs = payload.get("userErrors") or []
    if errs:
        raise NamedStop("SHOPIFY_REFUSED", "; ".join(e["message"] for e in errs), 1)
    return payload


# ---------- Search Console ----------
def gsc_token():
    if "gsc" not in _tokens:
        fix = "Owner: run the Google sign-in again (~/bin/gsc-signin.py) and re-save the secret."
        st, body = http("https://oauth2.googleapis.com/token", urllib.parse.urlencode({
            "client_id": env("GSC_OAUTH_CLIENT_ID_GLORY", fix), "client_secret": env("GSC_OAUTH_CLIENT_SECRET_GLORY", fix),
            "refresh_token": env("GSC_REFRESH_TOKEN_GLORY", fix), "grant_type": "refresh_token"}),
            {"Content-Type": "application/x-www-form-urlencoded"})
        if st != 200:
            raise NamedStop("GSC_TOKEN_REFUSED", f"Google refused the Search Console sign-in (HTTP {st}). {fix}", 3)
        _tokens["gsc"] = json.loads(body)["access_token"]
    return _tokens["gsc"]


def gsc(url, body=None):
    st, text = http(url, body, {"Authorization": "Bearer " + gsc_token()})
    if st != 200:
        raise NamedStop("GSC_API", f"Search Console answered HTTP {st}: {text[:200]}", 1)
    return json.loads(text)


def gsc_query(start, end, dimensions, row_limit=1000):
    site = urllib.parse.quote(GSC_SITE, safe="")
    return gsc(f"https://www.googleapis.com/webmasters/v3/sites/{site}/searchAnalytics/query",
               {"startDate": start, "endDate": end, "dimensions": dimensions, "rowLimit": row_limit}).get("rows", [])


def gsc_inspect(url):
    r = gsc("https://searchconsole.googleapis.com/v1/urlInspection/index:inspect", {"inspectionUrl": url, "siteUrl": GSC_SITE})
    return r.get("inspectionResult", {}).get("indexStatusResult", {})


# ---------- GitHub issues (GITHUB_TOKEN in Actions) ----------
def gh(path, body=None, method=None):
    repo = os.environ.get("GITHUB_REPOSITORY", "cbarksdale2/glory-search-loop")
    tok = env("GITHUB_TOKEN", "The workflow must pass GITHUB_TOKEN with issues: write.")
    st, text = http(f"https://api.github.com/repos/{repo}{path}", body,
                    {"Authorization": "Bearer " + tok, "Accept": "application/vnd.github+json"}, method=method)
    if st >= 300:
        raise NamedStop("SEND_REFUSED", f"GitHub refused {method or 'GET'} {path} (HTTP {st})", 9)
    return json.loads(text) if text else {}


# ---------- OpenRouter (free models only) ----------
def openrouter_free_models():
    st, text = http("https://openrouter.ai/api/v1/models")
    if st != 200:
        raise NamedStop("OPENROUTER_MODELS", f"model list HTTP {st}", 75)
    out = []
    for m in json.loads(text)["data"]:
        p = m.get("pricing", {})
        if m["id"].endswith(":free") and float(p.get("prompt", 1)) == 0 and float(p.get("completion", 1)) == 0:
            out.append(m["id"])
    return out


def openrouter_chat(model, messages, max_tokens=6000):
    key = env("OPENROUTER_API_KEY_GLORY_BLOG", "Owner: create a new $0-limit key at openrouter.ai and save it as the Actions secret.")
    if not model.endswith(":free"):
        raise NamedStop("PAID_MODEL_REFUSED", f"{model} is not a free model; the loop never spends money", 1)
    st, text = http("https://openrouter.ai/api/v1/chat/completions",
                    {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0.4},
                    {"Authorization": "Bearer " + key, "HTTP-Referer": SITE, "X-Title": "glory-search-loop"}, timeout=180, tries=1)
    if st != 200:
        return None, f"HTTP {st}: {text[:160]}"
    d = json.loads(text)
    try:
        return d["choices"][0]["message"]["content"], None
    except (KeyError, IndexError):
        return None, f"no content: {text[:160]}"


# ---------- IndexNow ----------
def indexnow_key():
    from .core import config
    return config("site.json")["indexnow_key"]


def indexnow_check_keyfile(fetch=None):
    """The key file must serve the key on glorybyus.com. Returns None or a NamedStop."""
    key = indexnow_key()
    fetch = fetch or (lambda u: http(u))
    st, body = fetch(f"{SITE}/{key}.txt")
    if st != 200 or body.strip() != key:
        return NamedStop("INDEXNOW_KEYFILE", f"the IndexNow key file at /{key}.txt answered {st} without the key; "
                         "pings are skipped and the sitemap carries discovery. Auto-fix: re-create the redirect (see RUNBOOK).", 1)
    return None


def indexnow_ping(urls):
    """Returns 'accepted (202)' etc. 403/422 mean the key is not accepted: reported, sitemap still carries discovery."""
    st, body = http("https://api.indexnow.org/indexnow",
                    {"host": "glorybyus.com", "key": indexnow_key(), "urlList": list(urls)})
    return st, body[:200]
