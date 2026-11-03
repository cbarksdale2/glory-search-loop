# Mutations for fixes 3, 4, 5, 6, 8, 11 (read by mutation_proof.py). (fix, file, exact text, broken, test module)
MUTATIONS = [
    ("3 kill switch", "loop/publish.py", '    if paused():\n        raise NamedStop("PAUSED"', '    if False:\n        raise NamedStop("PAUSED"', "test_fix03_gate_killswitch"),
    ("3 weekly cap", "loop/publish.py", "    if published_this_week():", "    if False:", "test_fix03_gate_killswitch"),
    ("3 gate claim words", "loop/gate.py", '(("claim word", brand["banned_claims"]), ', "(", "test_fix03_gate_killswitch"),
    ("3 undo ledger", "loop/publish.py", '"undo": {"op": "unpublish", "article_id": a["id"]}', '"undo": {"op": "none"}', "test_fix03_gate_killswitch"),
    ("4 SEO re-apply", "loop/heal.py", '        elif live["description"] != d["description"]:', "        elif False:", "test_fix04_seo_registry"),
    ("5 internal links", "loop/gate.py", "    if len(post_links) < need:", "    if False:", "test_fix05_orphans"),
    ("5 related refresh", "loop/publish.py", "        if new == lp[\"body\"] or lp[\"id\"] == skip_id:", "        if True:", "test_fix05_orphans"),
    ("6 IndexNow key check", "loop/clients.py", "    if st != 200 or body.strip() != key:", "    if st != 200:", "test_fix06_indexnow"),
    ("8 polish missing", "loop/publish.py", '    if not text.endswith("POLISH-COMPLETE"):', "    if False:", "test_fix08_polish_missing"),
    ("11 foundational never merged", "loop/heal.py", ' and p["slug"] not in foundational:', ":", "test_fix11_remedies"),
    ("11 re-ping not indexed", "loop/heal.py", "            if ix is False:", "            if False:", "test_fix11_remedies"),
]
