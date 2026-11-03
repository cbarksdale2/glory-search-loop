"""Parse the plain-text post format (config/post_format.md) and render page-shape HTML."""
import html
import json
import re

from .core import NamedStop, SITE

FIELDS = {"TITLE": "title", "META": "meta", "DEFINITION": "definition", "QUICK ANSWER": "quick", "BEST FOR": "best_for"}


def parse(text):
    text = re.sub(r"^```[a-z]*\n|```\s*$", "", text.strip(), flags=re.M)
    p = {"sections": [], "faq": [], "sources": []}
    lines = text.splitlines()
    cur, mode = None, "head"
    for ln in lines:
        s = ln.strip()
        m = re.match(r"^\**(TITLE|META|DEFINITION|QUICK ANSWER|BEST FOR)\**\s*:\s*(.+)$", s)
        if m and mode == "head":
            p[FIELDS[m.group(1)]] = m.group(2).strip()
            continue
        if re.match(r"^\**SOURCES\**\s*:", s):
            mode = "sources"; continue
        if mode == "sources":
            u = re.search(r"https?://\S+", s)
            if u:
                p["sources"].append(u.group(0).rstrip(").,"))
            continue
        if s.startswith("## "):
            h = s[3:].strip()
            if h.lower().startswith("frequently asked"):
                mode = "faq"; cur = None; continue
            mode = "body"; cur = [h, []]; p["sections"].append(cur); continue
        if s.startswith("### ") and mode == "faq":
            cur = [s[4:].strip(), []]; p["faq"].append(cur); continue
        if cur is not None:
            cur[1].append(ln)
    p["sections"] = [(h, "\n".join(b).strip()) for h, b in p["sections"]]
    p["faq"] = [(q, " ".join(x.strip() for x in a if x.strip())) for q, a in p["faq"]]
    for k in ("title", "meta", "definition", "quick"):
        if not p.get(k):
            raise NamedStop("POST_UNPARSEABLE", f"the draft has no {k.upper()} line", 1)
    return p


def all_text(p):
    parts = [p.get(k, "") for k in ("title", "meta", "definition", "quick", "best_for")]
    parts += [h + "\n" + b for h, b in p["sections"]] + [q + "\n" + a for q, a in p["faq"]]
    return "\n".join(parts)


def links(p):
    return re.findall(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", all_text(p))


def words(p):
    return len(re.findall(r"[A-Za-z0-9']+", re.sub(r"\]\([^)]*\)", "]", all_text(p))))


# ---------- render ----------
def inline(s):
    s = html.escape(s, quote=False)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", lambda m: f'<a href="{html.escape(m.group(2))}">{m.group(1)}</a>', s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def block(md):
    out, lst, rows = [], None, []

    def flush():
        nonlocal lst, rows
        if lst:
            out.append(f"<{lst[0]}>" + "".join(f"<li>{inline(i)}</li>" for i in lst[1]) + f"</{lst[0]}>")
        if rows:
            body = [r for r in rows if not re.match(r"^\|?\s*:?-{2,}", r)]
            cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in body]
            head, rest = cells[0], cells[1:]
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in head) + "</tr></thead><tbody>"
                       + "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in rest) + "</tbody></table>")
        lst, rows = None, []

    for ln in md.splitlines():
        s = ln.strip()
        m_ul, m_ol = re.match(r"^[-*]\s+(.+)", s), re.match(r"^\d+[.)]\s+(.+)", s)
        if s.startswith("|"):
            if lst: flush()
            rows.append(s); continue
        if rows: flush()
        if m_ul or m_ol:
            kind = "ul" if m_ul else "ol"
            if not lst or lst[0] != kind:
                flush(); lst = (kind, [])
            lst[1].append((m_ul or m_ol).group(1)); continue
        flush()
        if s.startswith("### "):
            out.append(f"<h3>{inline(s[4:])}</h3>")
        elif s:
            out.append(f"<p>{inline(s)}</p>")
    flush()
    return "\n".join(out)


def schema(p, url, published, modified, author):
    return [
        {"@context": "https://schema.org", "@type": "Article", "headline": p["title"], "description": p["meta"],
         "mainEntityOfPage": url, "datePublished": published, "dateModified": modified,
         "author": {"@type": "Organization", "name": author, "url": SITE},
         "publisher": {"@type": "Organization", "name": "Glory By Us", "url": SITE},
         "speakable": {"@type": "SpeakableSpecification", "cssSelector": [".glory-definition", ".glory-quick-answer", ".glory-faq"]}},
        {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", a)}}
            for q, a in p["faq"]]},
        {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": 1, "name": "Glory By Us", "item": SITE + "/"},
            {"@type": "ListItem", "position": 2, "name": "The Process", "item": SITE + "/blogs/the-process"},
            {"@type": "ListItem", "position": 3, "name": p["title"], "item": url}]},
    ]


def render(p, url, published, modified, author, cta, related=None):
    h = [f'<p class="glory-definition"><strong>{inline(p["definition"])}</strong></p>',
         "<h2>Quick answer</h2>", f'<p class="glory-quick-answer">{inline(p["quick"])}</p>']
    if p.get("best_for"):
        h.append(f"<p><em>What this guide is best for:</em> {inline(p['best_for'])}</p>")
    for q, b in p["sections"]:
        h += [f"<h2>{inline(q)}</h2>", block(b)]
    h.append('<h2>Frequently asked questions</h2><div class="glory-faq">')
    for q, a in p["faq"]:
        h += [f"<h3>{inline(q)}</h3>", f"<p>{inline(a)}</p>"]
    h.append("</div>")
    h.append(f'<p class="glory-next-step"><strong>Next step:</strong> <a href="{html.escape(cta["url"])}?utm_source=the-process&amp;utm_medium=blog&amp;utm_content={html.escape(cta["slug"])}">{html.escape(cta["label"])}</a></p>')
    h.append('<div class="glory-related">' + (related or "") + "</div>")
    if p["sources"]:
        h.append("<p><small>Sources: " + " · ".join(f'<a href="{html.escape(u)}">{html.escape(u.replace("https://", ""))}</a>' for u in p["sources"]) + "</small></p>")
    h.append(f"<p><small>By {html.escape(author)} · Published {published[:10]} · Updated {modified[:10]}</small></p>")
    h.append('<script type="application/ld+json">' + json.dumps(schema(p, url, published, modified, author), ensure_ascii=False).replace("</", "<\\/") + "</script>")
    return "\n".join(h)


def related_html(posts):
    """posts: [(title, url)] -> the 'More from The Process' list kept in every post (orphan prevention)."""
    if not posts:
        return ""
    return "<h2>More from The Process</h2><ul>" + "".join(f'<li><a href="{html.escape(u)}">{html.escape(t)}</a></li>' for t, u in posts) + "</ul>"


RELATED_RE = re.compile(r'<div class="glory-related">.*?</div>', re.S)


def replace_related(body, posts):
    new = '<div class="glory-related">' + related_html(posts) + "</div>"
    if RELATED_RE.search(body):
        return RELATED_RE.sub(lambda m: new, body, count=1)
    return body + "\n" + new
