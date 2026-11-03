"""Shared plumbing: named stops, home-clock time, state on disk, sentinels, HTTP.

Rule 0: no job exits 0 having done nothing. Every job returns a census line; a job that
examined nothing raises a NamedStop. Exit codes follow rule-zero-shapes:
0 done · 1 problems found · 2 nothing checked / not recorded · 3 owner-only credential
9 run did not complete / send refused · 75 could not verify (remote 5xx).
"""
import datetime as dt
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

HOME_TZ = ZoneInfo("America/New_York")
SITE = "https://glorybyus.com"
UA = "glory-search-loop/1.0 (+https://github.com/cbarksdale2/glory-search-loop)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class NamedStop(Exception):
    def __init__(self, code, message, exit_code=1):
        super().__init__(f"NAMED STOP [{code}] {message}")
        self.code = code
        self.exit_code = exit_code


# ---------- time on the home clock ----------
def now():
    fixed = os.environ.get("LOOP_NOW")  # tests pin the clock
    if fixed:
        return dt.datetime.fromisoformat(fixed).astimezone(HOME_TZ)
    return dt.datetime.now(HOME_TZ)


def local_date(t=None):
    return (t or now()).date().isoformat()


def iso_week(t=None):
    y, w, _ = (t or now()).isocalendar()
    return f"{y}-W{w:02d}"


def human_time(t):
    """'Mon 2 Nov, 9:05 am' on the home clock."""
    t = t.astimezone(HOME_TZ)
    h = t.strftime("%I").lstrip("0")
    return f"{t.strftime('%a')} {t.day} {t.strftime('%b')}, {h}:{t.strftime('%M')} {t.strftime('%p').lower()}"


# ---------- state (the loop-data branch, checked out into ./state) ----------
def state_dir():
    d = os.environ.get("LOOP_STATE") or os.path.join(ROOT, "state")
    os.makedirs(d, exist_ok=True)
    return d


def spath(*parts):
    p = os.path.join(state_dir(), *parts)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def read_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True, ensure_ascii=False)
    os.replace(tmp, path)


def config(name):
    with open(os.path.join(ROOT, "config", name)) as f:
        return json.load(f) if name.endswith(".json") else f.read()


# ---------- sentinels ----------
def write_sentinel(job, status, census, extra=None):
    t = now()
    rec = {"job": job, "status": status, "census": census, "local_date": local_date(t),
           "week": iso_week(t), "finished": t.isoformat()}
    rec.update(extra or {})
    write_json(spath("sentinels", f"{job}.json"), rec)
    return rec


def read_sentinel(job):
    return read_json(spath("sentinels", f"{job}.json"))


def sentinel_state(job, max_age_days):
    """'ran' / 'NOT RUN' / 'STOPPED: <code>' for the report. Missing is never 'ok'."""
    s = read_sentinel(job)
    if not s:
        return "NOT RUN", None
    finished = dt.datetime.fromisoformat(s["finished"])
    if (now() - finished).total_seconds() > max_age_days * 86400:
        return "NOT RUN", s
    if s["status"] != "ok":
        return f"STOPPED: {s['status']}", s
    return "ran", s


# ---------- ledger (every site change, with its undo) ----------
def ledger():
    p = spath("ledger.jsonl")
    if not os.path.exists(p):
        return []
    with open(p) as f:
        return [json.loads(line) for line in f if line.strip()]


def ledger_add(entry):
    if "undo" not in entry:
        raise NamedStop("NO_UNDO", f"ledger entry {entry.get('action')} has no undo; refusing to record a change that cannot be reversed", 9)
    entry = dict(entry)
    entry.setdefault("id", f"{local_date()}-{len(ledger()) + 1:03d}")
    entry.setdefault("at", now().isoformat())
    with open(spath("ledger.jsonl"), "a") as f:
        f.write(json.dumps(entry, sort_keys=True, ensure_ascii=False) + "\n")
    return entry


# ---------- HTTP ----------
def http(url, data=None, headers=None, method=None, timeout=45, tries=3):
    """Returns (status, body_text). Retries 5xx/timeouts; 5xx after retries = exit 75."""
    h = {"User-Agent": UA}
    h.update(headers or {})
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
        h.setdefault("Content-Type", "application/json")
    elif isinstance(data, str):
        data = data.encode()
    last = None
    for i in range(tries):
        try:
            r = urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=timeout)
            return r.status, r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code < 500 and e.code != 429:
                return e.code, body
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = str(e)
        time.sleep(2 * (i + 1))
    raise NamedStop("COULD_NOT_VERIFY", f"{urllib.parse.urlsplit(url).netloc} did not answer ({last}); the next run retries", 75)


def env(name, owner_fix):
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise NamedStop(f"MISSING_{name}", f"secret {name} is not set. {owner_fix}", 3)
    return v


NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")
