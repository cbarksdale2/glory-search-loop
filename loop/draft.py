"""Sun 20:00: draft this week's pick with an OpenRouter free model (fallback list).

Sentinel shape: the previous draft is deleted first; the reply must end with DRAFT-COMPLETE;
a reply without it is not saved. A draft is never published on its own: publish requires the
Claude polish (drafts/<slug>.polished.md).
"""
import glob
import json
import os

from . import clients, facts as factsmod
from .core import NamedStop, config, iso_week, read_json, spath, SITE

# Free models change often; the live list decides, this only orders it. Checked 2026-11-02.
PREFERRED = ["nvidia/nemotron-3-ultra-550b-a55b:free", "google/gemma-4-31b-it:free", "thinkingmachines/inkling:free",
             "nvidia/nemotron-3.5-super-vl:free", "google/gemma-4-26b-a4b-it:free", "thinkingmachines/inkling-small:free"]
NOT_FOR_WRITING = ("content-safety", "code", "lfm-2.5-2.6b", "omni")
END = "DRAFT-COMPLETE"


def completed(text):
    """The reply counts only if its last non-empty line is the completion line (markdown decoration allowed)."""
    lines = [l for l in (text or "").strip().splitlines() if l.strip()]
    return bool(lines) and lines[-1].strip(" *_`#>") == END


def other_posts():
    files = sorted(glob.glob(spath("collect", "*.json")))
    c = read_json(files[-1]) if files else {}
    arts = c.get("articles") if isinstance(c.get("articles"), list) else []
    h = config("site.json")["blog_handle"]
    return [{"title": a["title"], "url": f"{SITE}/blogs/{h}/{a['handle']}"} for a in arts if a["isPublished"]]


def build_prompt(pick, facts, others):
    return config("draft_prompt.md").format(
        title=pick["title"], products=", ".join(pick.get("products", [])),
        banned=", ".join(config("brand.json")["banned_claims"] + config("brand.json")["never_say"]),
        voice=config("voice.md"), facts=json.dumps(facts, indent=1, ensure_ascii=False),
        others="\n".join(f"- {o['title']}: {o['url']}" for o in others) or "(none yet)", format=config("post_format.md"))


def model_order(available):
    return [m for m in PREFERRED if m in available] + [m for m in available if m not in PREFERRED and not any(x in m for x in NOT_FOR_WRITING)]


def run(chat=None, models=None):
    pick = (read_json(spath("picks", f"{iso_week()}.json")) or {}).get("pick")
    if not pick:
        raise NamedStop("NO_PICK", "this week's pick was not made, so there is nothing to draft", 2)
    out = spath("drafts", f"{pick['slug']}.draft.md")
    if os.path.exists(out):
        os.remove(out)  # an old draft can never pass for this week's
    facts = factsmod.build()
    prompt = build_prompt(pick, facts, other_posts())
    chat = chat or clients.openrouter_chat
    tried = []
    for m in model_order(models if models is not None else clients.openrouter_free_models())[:6]:
        text, err = chat(m, [{"role": "user", "content": prompt}])
        if completed(text):
            body = "\n".join(text.strip().splitlines()[:-1]).rstrip()
            with open(out, "w") as f:
                f.write(body + "\n")
            return f"drafted '{pick['title']}' with {m} ({len(text.split())} words) after {len(tried)} failed model(s)"
        if text:  # kept for inspection, never used
            with open(spath("drafts", "failed", f"{pick['slug']}.{m.replace('/', '_')}.txt"), "w") as f:
                f.write(text)
        tried.append(f"{m}: {err or 'no completion line'}")
    raise NamedStop("DRAFT_DID_NOT_COMPLETE", "no free model finished the draft: " + " | ".join(tried)[:600], 9)
