"""Mon 09:30 watchdog + weekly report issue; daily heartbeat.

- Drops: current 28 days vs prior 28 days, only when the prior window is big enough to mean
  something (>= 50 impressions or >= 10 clicks). Brand query position change > 1.5.
- Job sentinels: missing or stale = NOT RUN, never 0.
- AI referrals from Clarity only when a token exists; otherwise 'not read: <why>'.
- The report is a GitHub issue (GitHub emails the owner). Green reports close themselves.
- Heartbeat: if no report for 8 days, a red 'loop is down' issue opens.
"""
import datetime as dt
import glob
import json
import os

from . import clients, precheck
from .core import (NamedStop, config, human_time, iso_week, ledger, now, read_json, sentinel_state, spath,
                   write_json)

JOBS = [("collect", 1.5, "the daily data collection"), ("pick", 8, "the Sunday topic pick"),
        ("draft", 8, "the Sunday draft"), ("polish", 8, "the Monday Claude polish"),
        ("publish", 8, "the Monday publish"), ("heal", 8, "the Monday heal pass")]


# ---------- numbers ----------
def meaningful(prior, thr):
    return prior.get("impressions", 0) >= thr["min_prior_impressions"] or prior.get("clicks", 0) >= thr["min_prior_clicks"]


def drop(cur, prior, thr):
    """A drop only counts when that metric's prior window was big enough; tiny numbers never alert."""
    out = []
    for m, floor in (("clicks", thr["min_prior_clicks"]), ("impressions", thr["min_prior_impressions"])):
        p, c = prior.get(m, 0), cur.get(m, 0)
        if p < floor:
            continue  # small numbers never alert
        if (p - c) / p >= thr["drop_ratio"]:
            out.append(f"{m} {int(p)} → {int(c)}")
    return out or None


def rows_by(rows, strip_query=False):
    """Key -> summed clicks/impressions. Pages drop the query string, so Shopping variants of one page add up."""
    out = {}
    for r in rows:
        k = r["keys"][0].split("?")[0] if strip_query else r["keys"][0]
        o = out.setdefault(k, {"clicks": 0, "impressions": 0, "position": r.get("position", 0)})
        o["clicks"] += r.get("clicks", 0)
        o["impressions"] += r.get("impressions", 0)
    return out


def analyse(collect, thr, brand_queries):
    """Returns (alerts, notes). Missing data is a note 'not read', never a zero."""
    alerts, notes = [], []
    g = collect.get("gsc") if collect else None
    if not g or "not_read" in g:
        notes.append("Search numbers: not read" + (f" ({g['not_read'][:120]})" if g else " (no collect file this week)"))
        return alerts, notes
    d = drop(g["current"]["totals"], g["prior"]["totals"], thr)
    if d:
        alerts.append("Whole site fell: " + ", ".join(d))
    cur, pri = rows_by(g["current"]["pages"], True), rows_by(g["prior"]["pages"], True)
    for page, prow in pri.items():
        d = drop(cur.get(page, {}), prow, thr)
        if d:
            alerts.append(f"{page.replace('https://glorybyus.com', '') or '/'} fell: " + ", ".join(d))
    cq, pq = rows_by(g["current"]["queries"]), rows_by(g["prior"]["queries"])
    for q in brand_queries:
        if q in cq and q in pq:
            ch = cq[q]["position"] - pq[q]["position"]
            if ch > thr["brand_position_change"]:
                alerts.append(f"Brand search '{q}' slipped from position {pq[q]['position']:.1f} to {cq[q]['position']:.1f}")
    return alerts, notes


def ai_referrals(token=None, fetch=None):
    """Clarity Data Export. Without a token: an honest 'not read', never 0."""
    token = token if token is not None else os.environ.get("CLARITY_EXPORT_TOKEN_GLORY", "").strip()
    if not token:
        return {"not_read": "no Clarity export token yet (owner step)"}
    fetch = fetch or (lambda: clients.http("https://www.clarity.ms/export-data/api/v1/project-live-insights?numOfDays=3&dimension1=ReferrerUrl",
                                           headers={"Authorization": "Bearer " + token}))
    st, body = fetch()
    if st != 200:
        return {"not_read": f"Clarity answered HTTP {st}"}
    found = {r: 0 for r in config("site.json")["ai_referrers"]}
    for metric in json.loads(body):
        for row in metric.get("information", []):
            ref = (row.get("ReferrerUrl") or "").lower()
            for r in found:
                if r in ref:
                    found[r] += int(row.get("totalSessionCount") or row.get("sessionsCount") or 0)
    return {"last_3_days": found}


# ---------- owner steps: told once, then one thin line ----------
def owner_steps(stops, notes):
    p = spath("owner_steps.json")
    seen = read_json(p, {})
    out = []
    for text in [str(s) for s in stops] + notes:
        key = text.split("]")[0] if text.startswith("NAMED STOP") else text.split(" ")[0]
        first = seen.setdefault(key, now().isoformat())
        days = (now() - dt.datetime.fromisoformat(first)).days
        out.append({"key": key, "text": text, "days": days, "new": days == 0})
    write_json(p, {k: v for k, v in seen.items() if any(o["key"] == k for o in out)})
    return out


# ---------- report ----------
def latest_collect():
    files = sorted(glob.glob(spath("collect", "*.json")))
    return read_json(files[-1]) if files else None


def build_report(collect, job_states, alerts, notes, steps, done, ai, posts):
    t = now()
    red = bool(alerts or steps or any(s != "ran" for s, _ in job_states.values()))
    lines = []
    if alerts:
        lines.append(f"Search dipped this week: {len(alerts)} drop(s) worth a look.")
    elif any(s != "ran" for s, _ in job_states.values()):
        lines.append("The loop missed a step this week; it is shown below.")
    else:
        lines.append("The loop ran every step this week and nothing dropped.")
    lines.append("")
    lines.append(f"**Decide ({len(steps)})**" if steps else "Nothing to decide — this is just so you know.")
    for s in steps:
        lines.append(f"- {s['text']}" if s["new"] else f"- Still yours to answer: {s['key']} · {s['days']} days")
    lines += ["", "**New this week**"]
    lines += [f"- {a}" for a in alerts] or ["- No drops (drops only count when last month had 50+ impressions or 10+ clicks)."]
    lines += ["", "**Posts**"]
    lines += [f"- {p}" for p in posts] or ["- No live posts yet."]
    lines += ["", "**Every job**"]
    for job, (state, s) in job_states.items():
        label = dict((j, l) for j, _, l in JOBS)[job]
        lines.append(f"- {label}: {state}" + (f" — {s['census']}" if s and state == 'ran' else ""))
    lines += ["", "**AI tools sending visitors** (ChatGPT, Perplexity, Copilot)"]
    lines.append(f"- not read: {ai['not_read']}" if "not_read" in ai else "- " + ", ".join(f"{k}: {v}" for k, v in ai["last_3_days"].items()) + " (last 3 days)")
    lines += [f"- {n}" for n in notes]
    lines += ["", "**Done for you**"]
    lines += [f"- {d}" for d in done] or ["- Nothing changed on the site this week."]
    lines += ["", f"Glory search loop · {human_time(t)} · pause everything by setting the repository variable LOOP_PAUSED to true · @cbarksdale2"]
    subject = f"{t.strftime('%A')} {t.day} {t.strftime('%b')}: " + (f"{len(steps)} to decide, {len(alerts)} drops" if red else "nothing to decide")
    return subject, "\n".join(lines), red


def done_lines(days=7):
    cut = now() - dt.timedelta(days=days)
    out = []
    for e in ledger():
        if dt.datetime.fromisoformat(e["at"]) >= cut:
            out.append(e.get("summary") or e["action"])
    return out


def post_lines(collect):
    if not collect or not isinstance(collect.get("articles"), list):
        return ["Post list: not read"]
    idx = collect.get("index_status") if isinstance(collect.get("index_status"), dict) else {}
    out = []
    for a in collect["articles"]:
        if not a["isPublished"]:
            continue
        path = f"/blogs/{config('site.json')['blog_handle']}/{a['handle']}"
        st = idx.get(path, {}).get("coverageState", "index status not read") if "not_read" not in idx else "index status not read"
        out.append(f"{a['title']} — {st} — https://glorybyus.com{path}")
    return out


def run(post=True):
    thr = config("site.json")["thresholds"]
    collect = latest_collect()
    alerts, notes = analyse(collect, thr, config("site.json")["brand_queries"])
    stops, pre_notes = precheck.run_all()
    heal = read_json(spath("heal", f"{iso_week()}.json"), {})
    steps = owner_steps(stops, pre_notes + heal.get("owner_actions", []))
    notes += [f"Heal could not read {p}" for p in heal.get("not_read", [])]
    jobs = {j: sentinel_state(j, age) for j, age, _ in JOBS}
    ai = ai_referrals()
    done = done_lines() + [r for r in heal.get("remedies", []) if not r.startswith("Put back")]
    subject, body, red = build_report(collect, jobs, alerts, notes, steps, done, ai, post_lines(collect))
    rec = {"week": iso_week(), "subject": subject, "body": body, "red": red, "at": now().isoformat()}
    if post:
        issue = clients.gh("/issues", {"title": subject, "body": body, "labels": ["loop-report"]}, method="POST")
        rec["issue"] = issue.get("html_url")
        for old in clients.gh("/issues?state=open&labels=loop-report&per_page=50"):
            if old["number"] != issue["number"]:
                clients.gh(f"/issues/{old['number']}", {"state": "closed"}, method="PATCH")
        if not red:
            clients.gh(f"/issues/{issue['number']}", {"state": "closed", "state_reason": "completed"}, method="PATCH")
    write_json(spath("reports", f"{iso_week()}.json"), rec)
    return f"report '{subject}' {'posted' if post else 'written'}: {len(alerts)} drops, {len(steps)} owner steps, {'red' if red else 'green, closed'}"


# ---------- heartbeat ----------
def newest_report_age_days():
    files = sorted(glob.glob(spath("reports", "*.json")), key=lambda f: read_json(f, {}).get("at", ""))
    if not files:
        return None
    at = dt.datetime.fromisoformat(read_json(files[-1])["at"])
    return (now() - at).total_seconds() / 86400


def heartbeat(post=True, started=None):
    """Red issue when no report for heartbeat_days. 'started' = loop start date, so a brand new loop is not red."""
    limit = config("site.json")["thresholds"]["heartbeat_days"]
    age = newest_report_age_days()
    if age is None and started:
        age = (now() - dt.datetime.fromisoformat(started)).total_seconds() / 86400
    down = age is None or age > limit
    if post:
        open_down = clients.gh("/issues?state=open&labels=loop-down&per_page=10")
        if down and not open_down:
            clients.gh("/issues", {"title": "Glory search loop is down: no weekly report for 8 days",
                                   "body": "What broke: no weekly report was written for 8 days.\n\nWhat we did: opened this issue; "
                                           "the next weekly Claude pass also checks this.\n\nStatus: open until a report is written. @cbarksdale2",
                                   "labels": ["loop-down"]}, method="POST")
        if not down:
            for i in open_down:
                clients.gh(f"/issues/{i['number']}", {"state": "closed"}, method="PATCH")
    return down, age
