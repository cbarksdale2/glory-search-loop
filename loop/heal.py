"""Mon 09:00: heal.

1. SEO registry: re-apply the owner-approved descriptions when the live page differs (backup +
   ledger undo + live re-check). Homepage title/description cannot be written by the API: drift
   there is a named owner step.
2. Posts at 2 / 4 / 8 weeks (each milestone once per post):
   - not indexed -> re-ping IndexNow (auto-remedy)
   - 4+ weeks and weak (< weak_post_impressions) -> queue a strengthen pass for the Claude routine
   - 8 weeks, zero impressions, and NOT one of the owner's foundational posts -> merge into the
     closest live post (redirect + unpublish, both undoable). Foundational posts are only strengthened.
3. Monthly (first Monday): queue the post with the most impressions and the lowest click rate.
Writes state/heal/<week>.json with 'remedies' (done for you) and 'owner_actions' (only he can).
"""
import datetime as dt
import glob
import html as htmllib
import re

from . import clients, gate
from .core import NamedStop, config, http, iso_week, ledger, ledger_add, now, read_json, spath, write_json, SITE

MILESTONES = (2, 4, 8)
SET_COLLECTION = """mutation($i:CollectionInput!){ collectionUpdate(input:$i){ collection{ id } userErrors{ field message } } }"""
SET_PAGE = """mutation($id:ID!,$p:PageUpdateInput!){ pageUpdate(id:$id, page:$p){ page{ id } userErrors{ field message } } }"""
SET_BLOG = """mutation($id:ID!,$b:BlogUpdateInput!){ blogUpdate(id:$id, blog:$b){ blog{ id } userErrors{ field message } } }"""
REDIRECT = """mutation($r:UrlRedirectInput!){ urlRedirectCreate(urlRedirect:$r){ urlRedirect{ id path target } userErrors{ field message } } }"""


def live_seo(path, fetch=None):
    fetch = fetch or (lambda u: http(u))
    st, body = fetch(SITE + path)
    if st != 200:
        return None
    t = re.search(r"<title>(.*?)</title>", body, re.S)
    m = re.search(r'<meta name="description" content="([^"]*)"', body)
    title = htmllib.unescape(re.sub(r"\s+", " ", t.group(1)).strip()) if t else None
    return {"title": title.rsplit(" – Glory By Us", 1)[0] if title else None, "description": htmllib.unescape(m.group(1)) if m else None}


def drift(registry, fetch=None):
    """Returns (to_apply, owner_actions, not_read)."""
    apply, owner, unread = [], [], []
    hp = registry["homepage"]
    live = live_seo(hp["path"], fetch)
    if live is None:
        unread.append(hp["path"])
    elif live["title"] != hp["title"] or live["description"] != hp["description"]:
        owner.append(f"Homepage title or description changed on the live site. Put back: title '{hp['title']}', "
                     f"description '{hp['description']}' (Shopify admin > Online Store > Preferences).")
    for d in registry["descriptions"]:
        live = live_seo(d["path"], fetch)
        if live is None:
            unread.append(d["path"])
        elif live["description"] != d["description"]:
            apply.append(dict(d, old=live["description"]))
    return apply, owner, unread


def write_description(target, value, gql=None):
    gql = gql or clients.gql
    mf = [{"namespace": "global", "key": "description_tag", "type": "single_line_text_field", "value": value}]
    if target["kind"] == "collection":
        r = gql(SET_COLLECTION, {"i": {"id": target["id"], "seo": {"description": value}}})["collectionUpdate"]
    elif target["kind"] == "page":
        r = gql(SET_PAGE, {"id": target["id"], "p": {"metafields": mf}})["pageUpdate"]
    elif target["kind"] == "blog":
        r = gql(SET_BLOG, {"id": target["id"], "b": {"metafields": mf}})["blogUpdate"]
    else:
        raise NamedStop("UNKNOWN_TARGET", target["kind"], 1)
    clients.user_errors(r)


def reapply_seo(gql=None, fetch=None, paused=False):
    apply, owner, unread = drift(config("seo_registry.json"), fetch)
    done = []
    for d in apply:
        if paused:
            owner.append(f"SEO description on {d['path']} drifted but the loop is paused, so it was not put back.")
            continue
        write_description(d, d["description"], gql)
        ledger_add({"action": "seo_reapply", "path": d["path"], "summary": f"Put back the approved description on {d['path']}",
                    "undo": {"op": "restore_description", "target": {k: d[k] for k in ('kind', 'id', 'path')}, "old": d["old"]}})
        done.append(f"Put back the approved description on {d['path']}")
    return done, owner, unread


def page_metrics(collect, url):
    g = (collect or {}).get("gsc") or {}
    if "current" not in g:
        return None
    imp = clk = 0
    for r in g["current"]["pages"]:
        if r["keys"][0].split("?")[0].rstrip("/") == url.rstrip("/"):
            imp += r["impressions"]; clk += r["clicks"]
    return {"impressions": imp, "clicks": clk}


def indexed(collect, url):
    idx = (collect or {}).get("index_status") or {}
    s = idx.get(url.replace(SITE, ""), {})
    if not s or "not_read" in idx:
        return None
    return s.get("verdict") == "PASS"


def post_actions(posts, collect, foundational, today, claimed):
    """Pure decision step. posts: [{"slug","url","published","article_id"}]. Returns list of actions."""
    thr = config("site.json")["thresholds"]["weak_post_impressions"]
    acts = []
    for p in posts:
        age_w = (today - dt.date.fromisoformat(p["published"][:10])).days // 7
        for m in MILESTONES:
            key = f"{p['slug']}-{m}w"
            if age_w < m or key in claimed:
                continue
            met, ix = page_metrics(collect, p["url"]), indexed(collect, p["url"])
            if met is None:
                acts.append({"key": key, "op": "note", "text": f"{p['slug']} {m}-week check: search numbers not read"})
                continue
            if ix is False:
                acts.append({"key": key, "op": "reping", "url": p["url"], "text": f"{p['slug']} not indexed at {m} weeks: asked IndexNow again"})
            if m >= 4 and met["impressions"] < thr:
                if m == 8 and met["impressions"] == 0 and p["slug"] not in foundational:
                    acts.append({"key": key, "op": "merge", "post": p, "text": f"{p['slug']} had no search impressions in 8 weeks: merged into the closest post"})
                else:
                    acts.append({"key": key, "op": "strengthen", "slug": p["slug"], "text": f"{p['slug']} is weak at {m} weeks ({met['impressions']} impressions): queued for a stronger rewrite"})
            if not any(a["key"] == key for a in acts):
                acts.append({"key": key, "op": "ok", "text": f"{p['slug']} {m}-week check: {met['impressions']} impressions, {met['clicks']} clicks"})
    return acts


def live_ledger_posts():
    state = {}
    for e in ledger():
        if e["action"] == "publish":
            state[e["slug"]] = {"slug": e["slug"], "url": e["url"], "published": e["at"], "article_id": e["article_id"]}
        elif e["action"] == "unpublish" or (e["action"] == "undo" and "publish" in (e.get("summary") or "").lower()):
            state.pop(e["slug"], None)
    return list(state.values())


def queue_strengthen(slug, why):
    q = read_json(spath("queue", "strengthen.json"), [])
    if not any(x["slug"] == slug for x in q):
        q.append({"slug": slug, "why": why, "queued": now().isoformat()})
        write_json(spath("queue", "strengthen.json"), q)


def run(gql=None):
    from .publish import paused
    gql = gql or clients.gql
    files = sorted(glob.glob(spath("collect", "*.json")))
    collect = read_json(files[-1]) if files else None
    remedies, owner, unread = reapply_seo(gql, paused=paused())
    claimed = set(read_json(spath("heal", "milestones.json"), []))
    foundational = {t["slug"] for t in config("topics.json")["ordered"]}
    posts = live_ledger_posts()
    acts = post_actions(posts, collect, foundational, now().date(), claimed)
    for a in acts:
        if a["op"] == "reping":
            try:
                clients.indexnow_ping([a["url"]])
            except NamedStop:
                pass
        elif a["op"] == "strengthen":
            queue_strengthen(a["slug"], a["text"])
        elif a["op"] == "merge" and not paused():
            others = [p for p in posts if p["slug"] != a["post"]["slug"]]
            if not others:
                a["text"] += " (skipped: no other post to merge into)"
            else:
                target = max(others, key=lambda o: gate.similarity(o["slug"].replace("-", " "), a["post"]["slug"].replace("-", " ")))
                r = clients.user_errors(gql(REDIRECT, {"r": {"path": a["post"]["url"].replace(SITE, ""), "target": target["url"].replace(SITE, "")}})["urlRedirectCreate"])
                from .rollback import UNPUBLISH
                clients.user_errors(gql(UNPUBLISH, {"id": a["post"]["article_id"]})["articleUpdate"])
                ledger_add({"action": "merge", "slug": a["post"]["slug"], "summary": a["text"],
                            "undo": {"op": "delete_redirect", "redirect_id": r["urlRedirect"]["id"]}})
                ledger_add({"action": "unpublish", "slug": a["post"]["slug"], "summary": f"Unpublished {a['post']['slug']} (merged)",
                            "undo": {"op": "republish", "article_id": a["post"]["article_id"]}})
        claimed.add(a["key"])
        if a["op"] != "ok":
            remedies.append(a["text"])
    if now().day <= 7 and collect and posts:
        scored = [(page_metrics(collect, p["url"]) or {"impressions": 0, "clicks": 0}, p) for p in posts]
        scored = [(m, p) for m, p in scored if m["impressions"] >= config("site.json")["thresholds"]["weak_post_impressions"]]
        if scored:
            m, p = min(scored, key=lambda x: (x[0]["clicks"] / max(1, x[0]["impressions"]), -x[0]["impressions"]))
            queue_strengthen(p["slug"], "monthly strengthen: most impressions, lowest click rate")
            remedies.append(f"Monthly: queued {p['slug']} for a stronger rewrite")
    write_json(spath("heal", "milestones.json"), sorted(claimed))
    write_json(spath("heal", f"{iso_week()}.json"), {"remedies": remedies, "owner_actions": owner, "not_read": unread, "at": now().isoformat()})
    checked = len(config("seo_registry.json")["descriptions"]) + 1 - len(unread)
    if checked == 0 and not posts:
        raise NamedStop("NOTHING_CHECKED", "heal could not read any live page and there are no posts", 2)
    return f"checked {checked} SEO values ({len(unread)} not read), {len(posts)} posts, {len(acts)} milestone checks; {len(remedies)} remedies, {len(owner)} owner steps"
