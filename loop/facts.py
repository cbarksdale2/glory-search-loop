"""facts.json: the ONLY facts a draft may use. Built from live product pages + config/brand.json.

Benefit sentences that carry a banned claim (circulation, follicles, growth, ...) are dropped
here, so a free model never sees them.
"""
import re

from . import clients
from .core import config, now, spath, write_json, SITE

HAIR = ["pomade-paste", "hydrating-conditioner", "brush-your-hair", "durag", "rosemary-myrrh-shampoo-body-bar",
        "glory-set", "scalp-health-varsity-set"]
Q = """query($h:String!){ productByHandle(handle:$h){ title handle status onlineStoreUrl description
 priceRangeV2{ minVariantPrice{ amount } } } }"""


def banned_re():
    words = config("brand.json")["banned_claims"] + config("brand.json")["never_say"]
    return re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b", re.I)


def ingredients(desc):
    m = re.search(r"Full Ingredient[^A-Z]*(?:Blend|Artisanal Blend)\s*(.+)$", desc)
    if not m:
        return []
    return [i.strip(" .") for i in m.group(1).split(",") if i.strip(" .")]


def clean_sentences(desc):
    bad = banned_re()
    body = re.split(r"Full Ingredient", desc)[0]
    sents = re.split(r"(?<=[.!?])\s+", body)
    return [s.strip() for s in sents if s.strip() and not bad.search(s) and len(s) < 400]


def build(fetch=None):
    fetch = fetch or (lambda h: clients.gql(Q, {"h": h})["productByHandle"])
    products = []
    for h in HAIR:
        p = fetch(h)
        if not p or p.get("status") != "ACTIVE" or not p.get("onlineStoreUrl"):
            continue
        products.append({"name": p["title"], "handle": h, "url": f"{SITE}/products/{h}",
                         "price_usd": p["priceRangeV2"]["minVariantPrice"]["amount"],
                         "ingredients": ingredients(p["description"]),
                         "page_lines": clean_sentences(p["description"])[:14]})
    if len(products) < 3:
        from .core import NamedStop
        raise NamedStop("FACTS_TOO_FEW", f"only {len(products)} hair products read from Shopify; drafting needs the live product pages", 2)
    facts = {"built_at": now().isoformat(), "source": "live Shopify product pages + config/brand.json",
             "brand": config("brand.json")["facts"], "products": products}
    write_json(spath("facts.json"), facts)
    return facts
