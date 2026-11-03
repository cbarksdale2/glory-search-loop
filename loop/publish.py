"""Mon 08:00: gate, then publish to the blog 'the-process'. Every site change is a ledger entry with its undo.

Refuses (named stops) when: LOOP_PAUSED=true (kill switch) · a post was already published this
ISO week (1/week cap) · the Claude polish is missing or older than the draft (skip the week; a
free-model-only draft is never published) · the gate finds any problem.
After publishing: every live post's 'More from The Process' list is refreshed (orphan
prevention), the page is verified live (200, title, canonical, schema, sitemap, not in the
site navigation), and IndexNow is pinged when the key file checks out.
"""
import datetime as dt
import glob
import json
import os
import re
import time

from . import clients, collect, gate, post as postmod
from .core import NamedStop, config, iso_week, ledger, ledger_add, now, read_json, spath, write_json, SITE

ARTICLES = """query($q:String!){ blogs(first:1, query:$q){ nodes{ id handle articles(first:100){ nodes{
 id handle title isPublished publishedAt body } } } } }"""
CREATE = """mutation($a:ArticleCreateInput!){ articleCreate(article:$a){ article{ id handle isPublished publishedAt } userErrors{ field message } } }"""
UPDATE = """mutation($id:ID!,$a:ArticleUpdateInput!){ articleUpdate(id:$id, article:$a){ article{ id handle isPublished } userErrors{ field message } } }"""


def paused():
    return (os.environ.get("LOOP_PAUSED") or "").strip().lower() in ("1", "true", "yes", "on")


def published_this_week():
    w = iso_week()
    return [e for e in ledger() if e["action"] == "publish" and iso_week(dt.datetime.fromisoformat(e["at"])) == w]


def polished_path(slug, kind="polished"):
    return spath("drafts", f"{slug}.{kind}.md")


def read_polished(slug, kind="polished", after=None):
    """The polish counts only if it exists, ends with POLISH-COMPLETE and is newer than the draft."""
    p, d = polished_path(slug, kind), spath("drafts", f"{slug}.draft.md")
    if not os.path.exists(p):
        return None, "no Claude polish file"
    text = open(p).read().rstrip()
    if not text.endswith("POLISH-COMPLETE"):
        return None, "the polish file has no completion line"
    if kind == "polished" and os.path.exists(d) and os.path.getmtime(p) < os.path.getmtime(d):
        return None, "the polish is older than this week's draft"
    return text[: -len("POLISH-COMPLETE")].rstrip(), None


def live_posts(gql):
    h = config("site.json")["blog_handle"]
    nodes = [b for b in gql(ARTICLES, {"q": f"handle:{h}"})["blogs"]["nodes"] if b["handle"] == h]
    if not nodes:
        raise NamedStop("BLOG_MISSING", "blog 'the-process' not found", 1)
    out = []
    for a in nodes[0]["articles"]["nodes"]:
        if a["isPublished"]:
            out.append({"id": a["id"], "slug": a["handle"], "title": a["title"], "url": f"{SITE}/blogs/{h}/{a['handle']}",
                        "text": re.sub(r"<[^>]+>", " ", a["body"] or ""), "body": a["body"] or "", "publishedAt": a["publishedAt"]})
    return out


def backup_body(article_id, body):
    p = spath("backups", f"{article_id.split('/')[-1]}-{now().strftime('%Y%m%dT%H%M%S')}.html")
    with open(p, "w") as f:
        f.write(body)
    return os.path.relpath(p, spath())


def refresh_related(gql, posts, skip_id=None):
    """Orphan prevention: every live post lists every other live post. Returns count updated."""
    n = 0
    for lp in posts:
        others = [(o["title"], o["url"]) for o in posts if o["id"] != lp["id"]]
        new = postmod.replace_related(lp["body"], others)
        if new == lp["body"] or lp["id"] == skip_id:
            continue
        bk = backup_body(lp["id"], lp["body"])
        clients.user_errors(gql(UPDATE, {"id": lp["id"], "a": {"body": new}})["articleUpdate"])
        ledger_add({"action": "update_related", "slug": lp["slug"], "article_id": lp["id"],
                    "summary": f"Linked '{lp['title']}' to the newest posts", "undo": {"op": "restore_body", "article_id": lp["id"], "backup": bk}})
        n += 1
    return n


def verify_live(url, fetch=None, tries=6):
    """Returns (facts, problems) for the live page."""
    fetch = fetch or (lambda u: clients.http(u + ("&" if "?" in u else "?") + f"v={int(time.time())}"))
    for i in range(tries):
        st, body = fetch(url)
        if st == 200:
            break
        time.sleep(10)
    f = collect.page_facts(url.replace(SITE, ""), body, st, url)
    probs = []
    if st != 200:
        probs.append(f"page answers {st}")
    if f["canonical"] and f["canonical"].rstrip("/") != url.rstrip("/"):
        probs.append(f"canonical points elsewhere: {f['canonical']}")
    for t in ("Article", "FAQPage", "BreadcrumbList"):
        if t not in f["schema_types"]:
            probs.append(f"{t} schema missing on the live page")
    nav = []
    for path in config("site.json")["nav_pages"]:
        s2, b2 = fetch(SITE + path)
        nav += [l for l in collect.page_facts(path, b2, s2, SITE + path)["blog_links"] if "/blogs/" in l]
    if nav:
        probs.append(f"blog visible to shoppers: {sorted(set(nav))}")
    try:
        f["in_sitemap"] = url in collect.sitemap_urls(fetch)
    except NamedStop as e:
        f["in_sitemap"] = f"not read: {e}"
    if f["in_sitemap"] is not True:
        probs.append("not in sitemap yet")
    return f, probs


def publish_new(gql, pick, text, facts):
    p = postmod.parse(text)
    posts = live_posts(gql)
    problems = gate.check(p, facts, posts, require_products=pick.get("products"))
    write_json(spath("gate", f"{iso_week()}-{pick['slug']}.json"), {"slug": pick["slug"], "problems": problems, "at": now().isoformat()})
    if problems:
        raise NamedStop("GATE_FAILED", f"'{pick['title']}' was not published: " + "; ".join(problems), 1)
    site = config("site.json")
    url = f"{SITE}/blogs/{site['blog_handle']}/{pick['slug']}"
    t = now().isoformat()
    prod = next((pr for pr in facts["products"] if pr["handle"] in pick.get("products", [])), facts["products"][0])
    body = postmod.render(p, url, t, t, site["article_author"], {"url": prod["url"], "label": f"Shop {prod['name']}", "slug": pick["slug"]},
                          postmod.related_html([(o["title"], o["url"]) for o in posts]))
    a = clients.user_errors(gql(CREATE, {"a": {
        "blogId": site["blog_id"], "title": p["title"], "handle": pick["slug"], "body": body, "summary": f"<p>{postmod.inline(p['quick'])}</p>",
        "author": {"name": site["article_author"]}, "isPublished": True, "tags": ["the-process", pick.get("kind", "post")],
        "metafields": [{"namespace": "global", "key": "description_tag", "type": "single_line_text_field", "value": p["meta"]},
                       {"namespace": "global", "key": "title_tag", "type": "single_line_text_field", "value": p["title"]}]}})["articleCreate"])["article"]
    ledger_add({"action": "publish", "slug": pick["slug"], "article_id": a["id"], "url": url,
                "summary": f"Published '{p['title']}' — {url}", "undo": {"op": "unpublish", "article_id": a["id"]}})
    new_list = posts + [{"id": a["id"], "slug": pick["slug"], "title": p["title"], "url": url, "body": body, "text": ""}]
    linked = refresh_related(gql, new_list, skip_id=a["id"])
    return url, linked


def apply_strengthen(gql, facts):
    """Queued rewrites (from heal) written by the Claude routine as drafts/<slug>.strengthen.md."""
    q = read_json(spath("queue", "strengthen.json"), [])
    done, notes, keep = 0, [], []
    posts = live_posts(gql) if q else []
    for item in q:
        text, why = read_polished(item["slug"], "strengthen")
        lp = next((x for x in posts if x["slug"] == item["slug"]), None)
        if not text or not lp:
            keep.append(item); continue
        p = postmod.parse(text)
        problems = gate.check(p, facts, [x for x in posts if x["slug"] != item["slug"]])
        if problems:
            notes.append(f"rewrite of {item['slug']} failed the gate: " + "; ".join(problems)); keep.append(item); continue
        site = config("site.json")
        prod = facts["products"][0]
        others = [(o["title"], o["url"]) for o in posts if o["slug"] != item["slug"]]
        body = postmod.render(p, lp["url"], lp["publishedAt"], now().isoformat(), site["article_author"],
                              {"url": prod["url"], "label": f"Shop {prod['name']}", "slug": item["slug"]}, postmod.related_html(others))
        bk = backup_body(lp["id"], lp["body"])
        clients.user_errors(gql(UPDATE, {"id": lp["id"], "a": {"body": body}})["articleUpdate"])
        ledger_add({"action": "strengthen", "slug": item["slug"], "article_id": lp["id"], "summary": f"Rewrote '{lp['title']}' stronger ({item['why']})",
                    "undo": {"op": "restore_body", "article_id": lp["id"], "backup": bk}})
        os.replace(polished_path(item["slug"], "strengthen"), spath("drafts", f"{item['slug']}.strengthen.applied-{now().strftime('%Y%m%d')}.md"))
        done += 1
    write_json(spath("queue", "strengthen.json"), keep)
    return done, notes


def run(gql=None, verify=True):
    gql = gql or clients.gql
    if paused():
        raise NamedStop("PAUSED", "LOOP_PAUSED is true: nothing was published (remove the repository variable to resume)", 0)
    facts0 = read_json(spath("facts.json"))
    rewrites, rnotes = apply_strengthen(gql, facts0) if facts0 else (0, [])
    pick = (read_json(spath("picks", f"{iso_week()}.json")) or {}).get("pick")
    if not pick:
        raise NamedStop("NO_PICK", "no pick this week, so nothing to publish", 2)
    if published_this_week():
        raise NamedStop("WEEKLY_CAP", "a post was already published this week (cap: 1 per week)", 0)
    text, why = read_polished(pick["slug"])
    if not text:
        raise NamedStop("POLISH_MISSING", f"skipped this week: {why}. A free-model-only draft is never published", 2)
    facts = read_json(spath("facts.json"))
    if not facts:
        raise NamedStop("NO_FACTS", "facts.json missing; the draft job builds it", 2)
    url, linked = publish_new(gql, pick, text, facts)
    line = f"published {url}; refreshed links in {linked} older post(s); {rewrites} rewrite(s) applied" + (f" ({'; '.join(rnotes)})" if rnotes else "")
    if verify:
        f, probs = verify_live(url)
        write_json(spath("verify", f"{pick['slug']}.json"), {"facts": f, "problems": probs, "at": now().isoformat()})
        ki = clients.indexnow_check_keyfile()
        ping = "skipped (key file not serving)" if ki else "%s %s" % clients.indexnow_ping([url, f"{SITE}/blogs/{config('site.json')['blog_handle']}"])
        line += f"; live check: {'ok' if not probs else '; '.join(probs)}; IndexNow: {ping}"
    return line
