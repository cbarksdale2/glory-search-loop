"""A fake Shopify that records mutations, and a known-good parsed post."""
import re
from loop import post as postmod

GOOD = """TITLE: Why is Pomade Paste good for beards?
META: Glory Pomade Paste gives beards a clean, light hold and shine. How to use it, how much, and how it fits a beard, curls and waves routine.
DEFINITION: Glory Pomade Paste is a whipped, light styling paste from Glory By Us made for textured hair. It gives beards, curls and waves hold and a clean, natural shine without grease, and it washes out clean, so it fits a daily beard routine.
QUICK ANSWER: Pomade Paste is good for beards because it lays stray hairs down with a light hold and a clean shine, without a greasy feel.
BEST FOR: anyone with a textured beard who wants it neat every day.

## Why use Pomade Paste on a beard?
It lays the beard down and keeps the shape. The paste is light and whipped, so the beard stays soft and neat. It works on beards, curls and waves alike.

## How do you apply Pomade Paste to a beard?
1. Warm a dime-sized amount between your palms.
2. Work it through the beard from root to tip.
3. Brush it down with the [Brush (Your Hair)](https://glorybyus.com/products/brush-your-hair).

## What is in Pomade Paste?
It lists shea butter, aloe vera, avocado oil and beeswax among its ingredients. See the [Pomade Paste](https://glorybyus.com/products/pomade-paste) page for the full list.

## Can you use it on waves and curls too?
Yes. Glory says the same jar works for waves, curls, beards, slick-backs and buns.


## What does a daily beard routine with Pomade Paste look like?
A daily routine is short: clean beard, a little paste, a brush, and you are done. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence one. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence two. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence three. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence four. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence five. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence six. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence seven. Step by step, a consistent routine keeps the beard shape clean and the line sharp, morning after morning, sentence eight.

## Why does the process matter as much as the product?
The process is the routine you repeat every day, and that repetition is what keeps a beard looking intentional. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part one. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part two. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part three. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part four. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part five. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part six. Commitment, consistency and dedication show up in the small things, like how you lay the beard down, part seven.

## How do you keep a beard neat between cuts?
Keep it neat by brushing it down every morning and using a light layer of paste to lay stray hairs. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note one. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note two. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note three. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note four. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note five. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note six. A quick brush through the beard and a fresh layer keep the shape between visits to the barber, note seven.
\n\n## Frequently asked questions
### How much Pomade Paste should I use on my beard?
Start with a dime-sized amount warmed between your palms, then add a little more only if the beard needs it. A light layer gives hold and shine without weighing the hair down or leaving it feeling heavy.
### Does Pomade Paste wash out?
Yes, the product page says it washes out clean, so it fits a daily beard routine.
### Can I brush my beard after applying it?
Yes. Brushing after applying lays every stray hair down and spreads the paste evenly through the beard.

SOURCES:
- https://glorybyus.com/products/pomade-paste
"""

FACTS = {"brand": ["Glory Pomade Paste works for waves, curls, beards, slick-backs and buns."],
         "products": [{"name": "Pomade Paste", "handle": "pomade-paste", "url": "https://glorybyus.com/products/pomade-paste", "price_usd": "30.0",
                       "ingredients": ["Water", "Aloe Vera Gel", "Shea Butter", "Beeswax", "Avocado Oil", "Vitamin E"], "page_lines": ["Warm a dime-sized amount."]},
                      {"name": "Brush (Your Hair)", "handle": "brush-your-hair", "url": "https://glorybyus.com/products/brush-your-hair", "price_usd": "30.0",
                       "ingredients": [], "page_lines": []}]}


def good():
    return postmod.parse(GOOD)


class FakeShop:
    def __init__(self, articles=None):
        self.articles = articles or []
        self.calls = []

    def __call__(self, q, v=None):
        m = re.search(r"\{\s*(\w+)\(", q)
        self.calls.append((m.group(1) if q.strip().startswith("mutation") and m else "query", v))
        if "articleCreate" in q:
            a = {"id": f"gid://shopify/Article/{len(self.articles) + 1}", "handle": v["a"]["handle"], "title": v["a"]["title"],
                 "isPublished": True, "publishedAt": "2026-11-02T10:00:00-05:00", "body": v["a"]["body"]}
            self.articles.append(a)
            return {"articleCreate": {"article": a, "userErrors": []}}
        if "articleUpdate" in q:
            return {"articleUpdate": {"article": {"id": v["id"]}, "userErrors": []}}
        if "blogs(" in q:
            return {"blogs": {"nodes": [{"id": "b", "handle": "the-process", "articles": {"nodes": list(self.articles)}}]}}
        for k in ("collectionUpdate", "pageUpdate", "blogUpdate", "urlRedirectCreate", "urlRedirectDelete"):
            if k in q:
                return {k: {"userErrors": [], "urlRedirect": {"id": "r1"}}}
        raise AssertionError("unexpected query " + q[:60])

    def mutations(self, name):
        return [v for n, v in self.calls if n == name]
