#!/usr/bin/env python3
"""Safety check for a PUBLIC repo: no secrets, tokens or private email addresses in tracked files.
Risk: this repo is public and the loop holds Shopify, Google and OpenRouter credentials.
  python3 scripts/safety_check.py            scan tracked files
  python3 scripts/safety_check.py --self-test prove the scanner catches each broken shape
"""
import re, subprocess, sys

SECRET = [
    ("shopify token", r"shp(at|ss|ca|pa)_[0-9a-fA-F]{16,}"),
    ("openrouter key", r"sk-or-v1-[0-9a-f]{20,}"),
    ("github token", r"gh[opsu]_[A-Za-z0-9]{30,}"),
    ("google api key", r"AIza[0-9A-Za-z_\-]{30,}"),
    ("google oauth secret", r"GOCSPX-[0-9A-Za-z_\-]{20,}"),
    ("google refresh token", r"1//0[0-9A-Za-z_\-]{30,}"),
    ("google access token", r"ya29\.[0-9A-Za-z_\-]{20,}"),
    ("private key", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ("anthropic key", r"sk-ant-[0-9A-Za-z_\-]{20,}"),
]
EMAIL = r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
PUBLIC_EMAILS = {"team@glorybyus.com", "noreply@anthropic.com"}  # on the live site / commit trailer


def scan(files):
    """files: {name: text} -> list of findings"""
    out = []
    for name, text in files.items():
        for label, pat in SECRET:
            if re.search(pat, text):
                out.append(f"{name}: looks like a {label}")
        for e in set(re.findall(EMAIL, text)):
            if e.lower() not in PUBLIC_EMAILS and not e.lower().endswith("@users.noreply.github.com"):
                out.append(f"{name}: private-looking email address {e}")
    return out


def tracked():
    names = subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split()
    files = {}
    for n in names:
        if n == "scripts/safety_check.py":
            continue
        try:
            files[n] = open(n, encoding="utf-8").read()
        except (UnicodeDecodeError, FileNotFoundError):
            pass
    return files


def self_test():
    real = {"x.py": "print('hello')", "c.json": '{"email":"team@glorybyus.com"}'}
    broken = [
        ("shopify token", {"a": "tok = 'shpat_" + "0123456789abcdef0123'"}),
        ("openrouter key", {"a": "sk-or-v1-" + "a" * 40}),
        ("google refresh token", {"a": "1//0" + "g" * 40}),
        ("google oauth secret", {"a": "GOCSPX-" + "x" * 28}),
        ("private email", {"a": "send to someone" + "@gmail.com"}),
        ("private key", {"a": "-----BEGIN RSA " + "PRIVATE KEY-----"}),
    ]
    if scan(real):
        print("NAMED STOP [SELF_TEST_FALSE_ALARM] clean files flagged:", scan(real)); return 1
    missed = [n for n, f in broken if not scan(f)]
    if missed:
        print(f"NAMED STOP [SELF_TEST_BLIND] not caught: {', '.join(missed)}", file=sys.stderr); return 1
    print(f"SELF-TEST OK — {len(broken)} broken shapes caught"); return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    files = tracked()
    if not files:
        print("NAMED STOP [NOTHING_SCANNED] no tracked files read", file=sys.stderr); return 2
    found = scan(files)
    for f in found:
        print("FAIL", f)
    print(f"scanned {len(files)} tracked files: {len(found)} problem(s)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
