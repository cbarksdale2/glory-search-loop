# Weekly Claude polish (Glory search loop) — one short pass, Monday 05:00 America/New_York

You are the ONLY human-quality check before a post goes live on glorybyus.com. Keep this pass short.
Repo: cbarksdale2/glory-search-loop. Work on the `loop-data` branch (state), read config from `main`.

## 1. Heartbeat (always, first)
- Look at the newest file in `reports/` on loop-data. If it is more than 8 days old, or there is none and the
  loop started before 2026-10-25, open a GitHub issue titled "Glory search loop is down: no weekly report for 8 days"
  with label `loop-down` (skip if one is already open), mentioning @cbarksdale2.
- If the `tick` workflow is disabled, re-enable it (`gh workflow enable tick.yml`).

## 2. Polish this week's draft
- This week = ISO week on the America/New_York clock. Read `picks/<week>.json` → slug.
- Read `drafts/<slug>.draft.md`, `facts.json`, and from main: `config/voice.md`, `config/post_format.md`, `config/brand.json`.
- If there is no draft: write `sentinels/polish.json` with status `NO_DRAFT` and stop.
- Rewrite into `drafts/<slug>.polished.md`, same format, ending with the line `POLISH-COMPLETE`:
  - **Bounds first**: delete every statement that FACTS does not support (benefits, mechanisms, "protects", "nourishes",
    ingredient effects). Ingredients may be listed, not given powers. No health, scalp-condition or growth talk.
    None of the banned words in brand.json. No other brand names. Never "plant-based".
  - Keep TITLE as the pick's title. 900–1300 words. 5–7 question H2s, 4–6 FAQ items (40–60 words each).
  - Link the pick's products with the URLs in FACTS, and every live post (latest `collect/*.json` articles).
  - Voice from voice.md: plain, direct, "you" and "we", routine and culture, no hype, no emojis.
- Strengthen queue: for each slug in `queue/strengthen.json` (max 1 per week), rewrite the live post the same way into
  `drafts/<slug>.strengthen.md` (ending `POLISH-COMPLETE`), adding the fan-out questions people search for.
- Write `sentinels/polish.json`: {"job":"polish","status":"ok","census":"polished <slug> (<n> words)","local_date":...,"week":...,"finished":<ISO time with offset>}.
- Commit to loop-data with message "polish <week>" and push. Never edit main. Never publish: Monday 08:00's code gate does that.

End your run with the line: POLISH-RUN-COMPLETE
