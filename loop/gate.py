"""The code gate: the only automatic check between a polished draft and the live site.

Fails on: banned claim words, never-say words, unsourced numbers, ingredients not on a Glory
product page, other brand names, out of scope, near-duplicate of a live post, no product link,
fewer than 3 FAQ items, missing definition, too few internal links, too short (< 75% of the
minimum; long never fails).
"""
import re

from . import post as postmod
from .core import NUM_RE, config, http, SITE


def _wre(words):
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)


def shingles(text, n=3):
    w = re.findall(r"[a-z']+", text.lower())
    return {" ".join(w[i:i + n]) for i in range(len(w) - n + 1)}


def similarity(a, b):
    A, B = shingles(a), shingles(b)
    return len(A & B) / max(1, len(A | B))


def source_numbers(urls, fetch=None):
    fetch = fetch or (lambda u: http(u))
    nums = set()
    for u in urls:
        try:
            st, body = fetch(u)
        except Exception:
            continue
        if st == 200:
            nums |= set(NUM_RE.findall(re.sub(r"<[^>]+>", " ", body)))
    return nums


def check(p, facts, live_posts, fetch=None, topics=None, require_products=None):
    """p: parsed post. facts: facts.json. live_posts: [{"slug","title","url","text"}]. Returns list of problems."""
    brand, topics = config("brand.json"), topics or config("topics.json")
    text = postmod.all_text(p)
    plain = re.sub(r"\]\([^)]*\)", "]", text)  # link targets are not prose
    probs = []

    for label, words in (("claim word", brand["banned_claims"]), ("never-say word", brand["never_say"]),
                         ("other brand name", brand["other_brands"]), ("out-of-scope topic", topics["excluded_terms"])):
        hits = sorted({m.group(0).lower() for m in _wre(words).finditer(plain)})
        if hits:
            probs.append(f"{label}: {', '.join(hits)}")

    scope = _wre(topics["scope_terms"])
    if len(scope.findall(plain)) < 5:
        probs.append("out of scope: barely about textured hair, waves, curls or beards")

    fact_text = str(facts)
    fact_nums = set(NUM_RE.findall(fact_text))
    allowed = fact_nums | {n.split(".")[0] for n in fact_nums} | source_numbers([u for u in p["sources"] if not u.startswith(SITE)], fetch)
    body_nums = set(NUM_RE.findall(re.sub(r"(?m)^\s*\d+[.)]\s", "", plain)))
    unsourced = sorted(n for n in body_nums if n not in allowed and n not in {"360"})
    if unsourced:
        probs.append(f"unsourced numbers: {', '.join(unsourced)}")

    glory_ings = " ".join(i.lower() for pr in facts["products"] for i in pr["ingredients"])
    bad_ing = sorted({w for w in brand["ingredient_vocab"] if re.search(r"\b" + re.escape(w) + r"\b", plain.lower()) and w not in glory_ings})
    if bad_ing:
        probs.append(f"ingredients not on any Glory product page: {', '.join(bad_ing)}")

    product_urls = {pr["url"] for pr in facts["products"]}
    linked = {u.split("?")[0].rstrip("/") for _, u in postmod.links(p)}
    if not linked & product_urls:
        probs.append("no link to a Glory product page")
    for h in (require_products or [])[:1]:
        u = f"{SITE}/products/{h}"
        if u in product_urls and u not in linked:
            probs.append(f"does not link its featured product {u}")
    stray = sorted(u for u in linked if u.startswith(SITE + "/products/") and u not in product_urls)
    if stray:
        probs.append(f"links to product pages not in facts: {', '.join(stray)}")

    if len(p["faq"]) < 3:
        probs.append(f"FAQ has {len(p['faq'])} questions (needs 3+)")
    if len(p.get("definition", "").split()) < 25:
        probs.append("definition missing or under 25 words")
    questions = sum(1 for h, _ in p["sections"] if h.endswith("?")) + len(p["faq"])
    if questions < int(brand["fanout_target"] * 0.75):
        probs.append(f"{questions} question headings/FAQ items (fan-out needs {brand['fanout_target']})")

    need = min(3, len(live_posts))
    post_links = linked & {lp["url"] for lp in live_posts}
    if len(post_links) < need:
        probs.append(f"links {len(post_links)} other posts (needs {need})")

    for lp in live_posts:
        if similarity(text, lp.get("text", "")) > 0.35:
            probs.append(f"near-duplicate of live post '{lp['title']}'")

    n = postmod.words(p)
    if n < brand["length"]["min_words"] * 0.75:
        probs.append(f"{n} words (minimum {brand['length']['min_words']}, fails below 75% of it)")
    return probs
