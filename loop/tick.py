"""One hourly GitHub Actions cron; the home clock decides what is due (never a fixed UTC hour).

Each job claims its slot (local date for daily jobs, ISO week for weekly ones) before running,
so a late or repeated tick never runs it twice; a failed run releases the claim (3 tries max).
Every job ends in a sentinel: ok + census, or the named stop's code. A job that returns no
census did nothing, which is itself a stop (rule 0).

  python -m loop.tick                 run whatever is due now
  python -m loop.tick --job collect   run one job now (manual), still writes its sentinel
"""
import argparse
import importlib
import os
import sys
import traceback

from .core import NamedStop, local_date, iso_week, now, read_json, spath, write_json, write_sentinel

# (job, weekday 0=Mon..6=Sun or None for daily, "HH:MM" home clock, module:function)
SCHEDULE = [
    ("collect", None, "06:00", "loop.collect:run"),
    ("heartbeat", None, "06:00", "loop.tick:heartbeat_job"),
    ("watchdog", 0, "09:30", "loop.watchdog:run"),
]
MAX_TRIES = 3


def heartbeat_job():
    from . import watchdog
    down, age = watchdog.heartbeat(started=os.environ.get("LOOP_STARTED", "2026-11-02T12:00:00-05:00"))
    return f"heartbeat: newest report {'none yet' if age is None else f'{age:.1f} days old'}; {'RED issue open' if down else 'ok'}"


def slot(weekday):
    return local_date() if weekday is None else iso_week()


def due(weekday, hhmm, t=None):
    t = t or now()
    if weekday is not None and t.weekday() != weekday:
        return False
    h, m = map(int, hhmm.split(":"))
    return (t.hour, t.minute) >= (h, m)  # catch-up runs until the end of that home-clock day


def resolve(target):
    mod, fn = target.split(":")
    return getattr(importlib.import_module(mod), fn)


def run_job(job, fn):
    """Runs fn, writes the sentinel. Returns (status, line). Never returns 'ok' without a census."""
    try:
        census = fn()
        if not census or not str(census).strip():
            raise NamedStop("NOTHING_DONE", f"{job} returned without saying what it did; treated as not run", 2)
        write_sentinel(job, "ok", str(census))
        return "ok", f"{job}: {census}"
    except NamedStop as e:
        write_sentinel(job, e.code, str(e), {"exit": e.exit_code})
        return e.code, f"{job}: {e}"
    except Exception as e:  # a crash is a bug: recorded, and the tick goes red
        write_sentinel(job, "CRASHED", f"{type(e).__name__}: {e}", {"exit": 9})
        traceback.print_exc()
        return "CRASHED", f"{job}: CRASHED {type(e).__name__}: {e}"


def claim(job, s):
    p = spath("claims", f"{job}-{s}.json")
    c = read_json(p, {"tries": 0, "done": False})
    if c["done"] or c["tries"] >= MAX_TRIES:
        return None
    c["tries"] += 1
    write_json(p, c)
    return p


def finish(p, ok):
    c = read_json(p)
    c["done"] = ok
    write_json(p, c)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--job")
    a = ap.parse_args(argv)
    lines, crashed = [], False
    for job, wd, hhmm, target in SCHEDULE:
        if a.job and job != a.job:
            continue
        if not a.job:
            if not due(wd, hhmm):
                continue
            p = claim(job, slot(wd))
            if not p:
                continue
        status, line = run_job(job, resolve(target))
        lines.append(line)
        crashed |= status == "CRASHED"
        if not a.job:
            finish(p, status == "ok")
    if a.job and not lines:
        print(f"NAMED STOP [UNKNOWN_JOB] no job called {a.job}", file=sys.stderr)
        return 2
    print("\n".join(lines) if lines else f"tick {now().strftime('%a %H:%M')} home clock: nothing due")
    return 9 if crashed else 0


if __name__ == "__main__":
    sys.exit(main())
