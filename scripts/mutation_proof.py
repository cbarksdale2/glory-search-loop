#!/usr/bin/env python3
"""Break each hostile-review fix once in a scratch copy and prove its test goes red.
A fix whose test stays green while the fix is broken is a blind test: NAMED STOP [TEST_BLIND].
  python3 scripts/mutation_proof.py
"""
import os, shutil, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# (fix, file, exact text in the real source, broken replacement, test module)
MUTATIONS = [
    ("1 sentinel", "loop/tick.py", "if not census or not str(census).strip():", "if False:", "test_fix01_sentinel"),
    ("2 small-number threshold", "loop/watchdog.py", "        if p < floor:\n            continue  # small numbers never alert\n", "", "test_fix02_thresholds"),
    ("7 credential pre-checks", "loop/precheck.py", "            stops.append(e)\n    for var", "            pass\n    for var", "test_fix07_precheck"),
    ("9 heartbeat", "loop/watchdog.py", "down = age is None or age > limit", "down = False", "test_fix09_heartbeat"),
    ("10 AI not read", "loop/watchdog.py", 'return {"not_read": "no Clarity export token yet (owner step)"}', 'return {"last_3_days": {}}', "test_fix10_ai_visibility"),
]
EXTRA = os.path.join(ROOT, "scripts", "mutations_extra.py")
if os.path.exists(EXTRA):
    ns = {}
    exec(open(EXTRA).read(), ns)
    MUTATIONS += ns["MUTATIONS"]


def run_test(d, mod):
    return subprocess.run([sys.executable, "-m", "unittest", mod], cwd=os.path.join(d, "tests"),
                          capture_output=True, text=True, env={**os.environ, "PYTHONPATH": d}).returncode


def main():
    blind, n = [], 0
    for fix, f, old, new, mod in MUTATIONS:
        d = tempfile.mkdtemp()
        try:
            shutil.copytree(ROOT, d, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git", "state", "__pycache__"))
            p = os.path.join(d, f)
            src = open(p).read()
            if src.count(old) != 1:
                print(f"NAMED STOP [MUTATION_STALE] fix {fix}: the text to break is no longer in {f} exactly once; update MUTATIONS", file=sys.stderr)
                return 1
            if run_test(d, mod) != 0:
                print(f"NAMED STOP [TEST_RED_BEFORE_BREAK] {mod} fails on the real source", file=sys.stderr); return 1
            open(p, "w").write(src.replace(old, new))
            if run_test(d, mod) == 0:
                blind.append(fix)
            n += 1
        finally:
            shutil.rmtree(d, ignore_errors=True)
    if not n:
        print("NAMED STOP [NOTHING_MUTATED] no mutations ran", file=sys.stderr); return 2
    if blind:
        print(f"NAMED STOP [TEST_BLIND] still green with the fix broken: {', '.join(blind)}", file=sys.stderr); return 1
    print(f"MUTATION PROOF OK — {n} fixes broken once, each test went red")
    return 0


if __name__ == "__main__":
    sys.exit(main())
