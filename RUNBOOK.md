# RUNBOOK — glory-search-loop

The hands-off blog + search-monitoring loop for glorybyus.com. All times America/New_York.

## Where things live
- **Code**: `main` (this branch). Python standard library only; no dependencies.
- **State**: branch `loop-data` (collect files, sentinels, claims, drafts, ledger, reports). Checked out into `./state` by the tick workflow. Never merged into main.
- **Secrets**: GitHub Actions secrets, piped from the owner's vault (`vault run -- sh -c 'printf %s "$X" | gh secret set X -R cbarksdale2/glory-search-loop'`). Nothing secret is in the repo.

## Jobs (one hourly cron, `tick.yml`; the code decides what is due on the home clock)
| When (ET) | Job | Writes |
|---|---|---|
| Daily 06:00 | collect | `collect/<date>.json`: Search Console 28d vs prior 28d, index status of posts, Shopify article list, live crawl, sitemap |
| Daily 06:00 | heartbeat | red issue "loop is down" when no weekly report for 8 days |
| Sun 18:00 | pick | `picks/<week>.json` |
| Sun 20:00 | draft | `drafts/<slug>.draft.md` (OpenRouter free models) |
| Mon 05:00 | polish | Claude weekly routine writes `drafts/<slug>.polished.md` + `sentinels/polish.json` |
| Mon 08:00 | publish | gate → Shopify article in blog `the-process` → ledger entry with undo |
| Mon 09:00 | heal | 2/4/8-week checks, SEO registry re-apply |
| Mon 09:30 | watchdog | weekly report issue (closes itself when green) |

A job claims its slot (date or ISO week) before running; a failure releases it for the next tick (3 tries).
Every job ends in `sentinels/<job>.json`; missing or stale = **NOT RUN** in the report.

## Operate
- **Run one job now**: Actions → tick → Run workflow → job = `collect` (or `gh workflow run tick.yml -f job=collect`).
- **Pause everything that writes to the site**: repository variable `LOOP_PAUSED=true` (`gh variable set LOOP_PAUSED -b true`). Remove it to resume.
- **Undo a site change**: Actions → rollback → ref = `last` or a ledger id (`python -m loop.rollback --list` shows them). Every publish, link refresh, SEO re-apply, merge and rewrite is in `loop-data/ledger.jsonl` with its undo.
- **Weekly Claude pass**: a scheduled Claude routine (Mon 05:00 ET) follows `config/polish_prompt.md`: heartbeat check, polish this week's draft into `drafts/<slug>.polished.md`, one queued rewrite. If it does not run, Monday's publish skips the week (named stop POLISH_MISSING) and the report says so.
- **Gate rules**: `loop/gate.py` with word lists in `config/brand.json` (banned claims, never-say, other brands, ingredient vocabulary) and scope/exclusions in `config/topics.json`.
- **Tests**: `cd tests && python3 -m unittest discover`; safety: `python3 scripts/safety_check.py && python3 scripts/safety_check.py --self-test`; mutation proof: `python3 scripts/mutation_proof.py`.
- **Land a change**: worktree → PR → `land <pr>` (merge gate = `ci.yml`, under 5 minutes). There is no deploy step: the next tick runs the merged code (`.land` says `DEPLOY=none`).

## Exit codes / named stops
0 done · 1 problems found · 2 nothing checked · 3 owner-only credential · 9 did not complete · 75 could not verify.
`NAMED STOP [CODE] what happened and the next step`.

## Known limits
- Homepage title/description live in Online Store → Preferences; the Admin API cannot write them, so drift there is reported as an owner step.
- IndexNow key: Shopify file `/cdn/shop/files/<key>.txt` plus a URL redirect from `/<key>.txt`. If the key is ever rejected, pings are skipped and the sitemap carries discovery.
