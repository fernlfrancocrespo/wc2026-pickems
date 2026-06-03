# Backend — Cloudflare Pages + Functions + D1

The site is a static front end (`index.html`, `i18n.js`, `data/*.json`) plus an API
that lives in `./functions` and runs on the **same origin** as the site (no CORS).
Storage is **Cloudflare D1** (SQLite).

```
functions/api/submit.js    POST  → insert one locked-in entry
functions/api/results.js   GET   → all entries for the leaderboard (no name/email)
functions/api/_utils.js    shared helpers
schema.sql                 D1 table
wrangler.toml              Pages + D1 config
```

## Prerequisites (one-time, machine setup)

1. **Install Node.js** (includes `npm`/`npx`) — LTS from https://nodejs.org. Verify:
   ```
   node -v
   npm -v
   ```
2. Open a terminal **in the project folder** for everything below.

## One-time setup

1. **Install Wrangler & log in** (opens a browser to authorize Cloudflare)
   ```
   npm install
   npx wrangler login
   ```

2. **Create the D1 database**
   ```
   npx wrangler d1 create wc2026
   ```
   Copy the printed `database_id` into `wrangler.toml` (the `PASTE_D1_DATABASE_ID_HERE` line).

3. **Create the table** (local + remote)
   ```
   npm run db:init:local
   npm run db:init:remote
   ```

## Run locally

```
npm run dev
```
Wrangler serves the static site **and** the `/api/*` functions on one origin (usually
`http://localhost:8788`) with a local D1. Fill the form, lock it in — the entry lands
in your local D1 and you get the share link.

Inspect local rows:
```
npx wrangler d1 execute wc2026 --local --command "SELECT created_at, display_name, country FROM submissions"
```

## Deploy

```
npm run deploy
```
(or connect the repo in the Cloudflare dashboard → Pages → it auto-builds on push).
After the first deploy, bind the D1 database to the Pages project in the dashboard
(**Settings → Functions → D1 bindings**: variable `DB` → `wc2026`) if it isn't already
picked up from `wrangler.toml`.

## Optional knobs (Pages → Settings → Environment variables / Secrets)

| Name | Type | Effect |
|------|------|--------|
| `MAX_SUBMISSIONS` | var | Hard cap on total entries. At the cap, `/api/submit` returns `closed` (423). Lower it to pause intake; this is your "shut it down" lever. |
| `ENTRY_CODE` | secret | If set, submissions must include a matching `code`. Put the same value in `ENTRY_CODE` at the top of `index.html` to send it. Keeps drive-by spam out. |
| `RESULTS_TOKEN` | secret | If set, `/api/results` requires `?token=...`. Use to keep the raw results private to you. |
| `SALT` | secret | Salt for the one-way IP hash stored with each row (abuse signal only). |

Set a secret:
```
npx wrangler pages secret put ENTRY_CODE
```

## Updating scores during the tournament (daily workflow)

Two host-maintained files drive the live pages. Edit them, run the scraper, redeploy.

**1. Live group standings** (`data/live.json`, shown on `/standings.html`)
- Add played results to `data/results_source.txt`, one per line: `Mexico 2-1 South Africa`
- Rebuild:  `python scrape.py --only results --results-txt data/results_source.txt`

**2. Pick-'ems scoring** (`data/answer_key.json`, powers the Leaderboard "Live scores")
- Fill in real outcomes as they're known (champion, award winners, the banded numbers,
  and `q8` = the real final 1–4 order per group). Leave anything unknown as `null`.
- The leaderboard auto-computes and ranks everyone the moment any value is filled in.
  Scoring rules live in `scoring.js` (exact picks = all-or-nothing; bands = full if the
  number is in your band, half if one band away; groups = +2 per real top-2 team, +2 perfect order).

Then redeploy: `npm run deploy` (live.json + answer_key.json ship as static files).

## Clearing the database (before going wide / after testing)
```
npx wrangler d1 execute wc2026 --remote --command "DELETE FROM submissions"
```

## Privacy / data notes
- The **share link** is fully client-side and never contains email.
- `/api/results` returns only `display_name` (e.g. `fernandof`), `country`, `lang`, and
  answers — **never** the full name or email (those stay in private D1 columns).
- IPs are stored only as a salted SHA-256 hash.
