"""Daily 06:00: Search Console rows, index status of posts, Shopify article list, live crawl.

Writes state/collect/<local date>.json. A source that fails writes {"not_read": "<reason>"},
never zeros and never yesterday's value.
"""
import datetime as dt
import html as htmllib
import json
import re

from . import clients
from .core import NamedStop, config, http, local_date, now, spath, write_json, SITE

ARTICLES_Q = """query($q:String!){ blogs(first:1, query:$q){ nodes{ id handle articles(first:100){ nodes{
 id handle title isPublished publishedAt updatedAt tags body summary } } } } }"""


def windows(today):
    """28-day window ending 3 days back, and the 28 days before it (Search Console lag)."""
    end = today - dt.timedelta(days=3)
    start = end - dt.timedelta(days=27)
    p_end = start - dt.timedelta(days=1)
    p_start = p_end - dt.timedelta(days=27)
    f = lambda d: d.isoformat()
    return {"current": [f(start), f(end)], "prior": [f(p_start), f(p_end)]}


def guard(fn):
    try:
        return fn()
    except NamedStop as e:
        return {"not_read": str(e)}
    except Exception as e:  # a broken source is a named cell, not a crash of the whole collect
        return {"not_read": f"{type(e).__name__}: {e}"[:300]}


def gsc_block(win):
    out = {"windows": win}
    for name, (s, e) in win.items():
        out[name] = {"queries": clients.gsc_query(s, e, ["query"]), "pages": clients.gsc_query(s, e, ["page"]),
                     "totals": (clients.gsc_query(s, e, []) or [{"clicks": 0, "impressions": 0}])[0]}
    return out


def articles():
    h = config("site.json")["blog_handle"]
    nodes = [b for b in clients.gql(ARTICLES_Q, {"q": f"handle:{h}"})["blogs"]["nodes"] if b["handle"] == h]
    b = nodes[0] if nodes else None
    if not b:
        raise NamedStop("BLOG_MISSING", "the blog 'the-process' was not found in Shopify", 1)
    return b["articles"]["nodes"]


def page_facts(path, html, status, final_url):
    t = re.search(r"<title>(.*?)</title>", html, re.S)
    canon = re.search(r'<link rel="canonical" href="([^"]+)"', html)
    meta = re.search(r'<meta name="description" content="([^"]*)"', html)
    ld_types = re.findall(r'"@type"\s*:\s*"([A-Za-z]+)"', " ".join(re.findall(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)))
    return {"path": path, "status": status, "final_url": final_url,
            "title": htmllib.unescape(re.sub(r"\s+", " ", t.group(1)).strip()) if t else None,
            "canonical": canon.group(1) if canon else None,
            "meta_description": htmllib.unescape(meta.group(1)) if meta else None,
            "schema_types": sorted(set(ld_types)),
            "clarity_tag": config("site.json")["clarity_tag"] in html,
            "blog_links": sorted(set(re.findall(r'href="([^"]*/blogs/[^"#?]*)', html)))}


def crawl(paths, fetch=None):
    fetch = fetch or (lambda u: http(u))
    out = {}
    for p in paths:
        st, html = fetch(SITE + p)
        out[p] = page_facts(p, html, st, SITE + p)
    return out


def sitemap_urls(fetch=None):
    fetch = fetch or (lambda u: http(u))
    st, idx = fetch(SITE + "/sitemap.xml")
    if st != 200:
        raise NamedStop("SITEMAP", f"sitemap.xml answered {st}", 1)
    urls = []
    for sm in re.findall(r"<loc>([^<]+sitemap_blogs[^<]*)</loc>", idx):
        st, body = fetch(sm.replace("&amp;", "&"))
        urls += re.findall(r"<loc>([^<]+)</loc>", body)
    return urls


def run():
    today = now().date()
    rec = {"local_date": local_date(), "collected_at": now().isoformat()}
    rec["gsc"] = guard(lambda: gsc_block(windows(today)))
    rec["articles"] = guard(articles)
    posts = [] if isinstance(rec["articles"], dict) else [a for a in rec["articles"] if a["isPublished"]]
    post_paths = [f"/blogs/{config('site.json')['blog_handle']}/{a['handle']}" for a in posts]
    rec["crawl"] = guard(lambda: crawl(config("site.json")["crawl_pages"] + post_paths))
    rec["sitemap_blog_urls"] = guard(sitemap_urls)
    rec["index_status"] = guard(lambda: {p: clients.gsc_inspect(SITE + p) for p in post_paths})
    write_json(spath("collect", f"{rec['local_date']}.json"), rec)

    read = [k for k in ("gsc", "articles", "crawl", "sitemap_blog_urls", "index_status") if not (isinstance(rec[k], dict) and "not_read" in rec[k])]
    if not read:
        raise NamedStop("NOTHING_READ", "collect read no source at all; every source failed (see the not_read cells)", 2)
    missing = 5 - len(read)
    q = 0 if isinstance(rec["gsc"], dict) and "not_read" in rec["gsc"] else len(rec["gsc"]["current"]["queries"])
    return f"collected {len(read)}/5 sources: {q} search queries, {len(posts)} live posts, {len(post_paths) + len(config('site.json')['crawl_pages'])} pages crawled" + (f"; {missing} source(s) not read" if missing else "")
