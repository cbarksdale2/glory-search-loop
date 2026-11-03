"""Sun 18:00: choose this week's post.

Candidates come from Search Console queries (latest collect) and Google autocomplete (free).
Everything passes the scope filter (textured / Black hair) and the exclusion list (health,
hair loss, transplants, custom durags). The owner's ordered list goes first; only once it is
used up does measured demand pick the topic.
"""
import glob
import json
import re
import urllib.parse

from .core import NamedStop, config, http, iso_week, ledger, read_json, spath, write_json

SEEDS = ["pomade for beard", "wave brush", "how often brush waves", "durag for waves", "wolfing waves",
         "pomade for curls", "how often wash textured hair", "slick back curly hair", "360 waves routine"]


def in_scope(text, topics=None):
    t = (topics or config("topics.json"))
    s = text.lower()
    if any(re.search(r"\b" + re.escape(x) + r"\b", s) for x in t["excluded_terms"] + config("brand.json")["other_brands"]):
        return False
    return any(re.search(r"\b" + re.escape(w) + r"\b", s) for w in t["scope_terms"])


def published_slugs():
    live = {}
    for e in ledger():
        if e["action"] == "publish":
            live[e["slug"]] = True
        if e["action"] == "undo" and e.get("slug"):
            live[e["slug"]] = False
    return {s for s, v in live.items() if v}


def autocomplete(seed):
    st, body = http("https://suggestqueries.google.com/complete/search?client=firefox&hl=en&gl=us&q=" + urllib.parse.quote(seed))
    return json.loads(body)[1] if st == 200 else []


def candidates(collect, suggest=autocomplete):
    out, notes = {}, []
    g = (collect or {}).get("gsc") or {}
    if "current" in g:
        for r in g["current"]["queries"]:
            out[r["keys"][0]] = {"source": "search console", "impressions": r["impressions"]}
    else:
        notes.append("search console queries not read")
    try:
        for s in SEEDS:
            for q in suggest(s):
                out.setdefault(q, {"source": "autocomplete", "impressions": 0})
    except NamedStop as e:
        notes.append(f"autocomplete not read: {e}")
    return {q: v for q, v in out.items() if in_scope(q)}, notes


def choose(topics, done, cands):
    for t in topics["ordered"]:
        if t["slug"] not in done and not any(x in t["title"].lower() for x in topics["excluded_terms"]):
            return dict(t, why="next on the owner's ordered list")
    best = sorted(((v["impressions"], q) for q, v in cands.items()), reverse=True)
    for imp, q in best:
        slug = re.sub(r"[^a-z0-9]+", "-", q.lower()).strip("-")
        if slug not in done:
            return {"slug": slug, "title": q[0].upper() + q[1:] + ("?" if q.split()[0] in ("how", "why", "what", "can", "does", "is") else ""),
                    "products": ["pomade-paste"], "kind": "demand", "why": f"measured demand: {imp} impressions"}
    return None


def run():
    files = sorted(glob.glob(spath("collect", "*.json")))
    collect = read_json(files[-1]) if files else None
    cands, notes = candidates(collect)
    pick = choose(config("topics.json"), published_slugs(), cands)
    if not pick:
        raise NamedStop("NOTHING_TO_PICK", "no in-scope topic left that is not already published", 2)
    rec = {"week": iso_week(), "pick": pick, "candidates": len(cands), "notes": notes,
           "top_candidates": sorted(cands, key=lambda q: -cands[q]["impressions"])[:20]}
    write_json(spath("picks", f"{iso_week()}.json"), rec)
    return f"picked '{pick['title']}' ({pick['why']}) from {len(cands)} in-scope candidates" + (f"; {'; '.join(notes)}" if notes else "")
