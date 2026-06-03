# World Cup 2026 Pick-'Ems

A prediction game for the 2026 FIFA World Cup (June 11 to July 19), in the spirit of a
League of Legends Worlds pick-'ems crossed with a March Madness bracket. You answer 22
questions before the opening kickoff (the champion, the order of every group, tournament
props, the big award winners), everything locks at kickoff, and you get a short shareable
link to your entry. Scores update as real results come in.

Live at **https://wc2026-pickems.com**. Fully bilingual (English / 🇧🇷 Português).

No accounts, no logins, no money, no betting. Email is collected only so you can edit your
entry; it is never shown publicly, never put in a share link, and never shared.

## How it works (architecture)

```
 scrape.py  ──►  data/*.json  ──►  static pages (index/leaderboard/standings/faq)
 (Python)        (committed)       i18n.js + scoring.js
                                          │
                          fetch │         │ POST /api/submit
                                ▼         ▼
                      Cloudflare Pages Functions (functions/api/*)  ──►  D1 (SQLite)
```

- **Front end:** plain HTML/CSS/vanilla JS, no build step and no framework. `i18n.js` is a
  shared translation layer and `scoring.js` a shared scoring engine, included on each page.
- **Data:** `scrape.py` pulls teams, rosters, FIFA ranks, recent form, the schedule, and
  player photos from public sources (mostly Wikipedia) into `data/*.json`, which the pages
  read directly. No live third-party calls from the browser except flag/photo images.
- **Backend:** Cloudflare Pages Functions (same-origin, no CORS) write submissions to a
  Cloudflare D1 (SQLite) database. A submission's full picks are also encoded into the
  `/p/<code>` share link, so viewing an entry needs no lookup.
- **Hosting:** Cloudflare Pages. Static files at the repo root, API under `functions/`.

## Pages
| File | What it is |
|------|------------|
| `index.html` | The form: 22 questions (champion, group drag-rankings, banded props, player-award photo cards). Also renders any shared entry read-only at `/p/<code>`. |
| `leaderboard.html` | Consensus, popular picks, group winners, an expandable full breakdown, participants, and live scores (once the answer key is filled in). |
| `standings.html` | Live group-stage tables, built from match results. |
| `faq.html` | Rules, scoring, prize, privacy, support. |
| `i18n.js` | Shared EN/PT dictionary plus `t()` / `teamLabel()` helpers. |
| `scoring.js` | Shared scoring engine (exact picks, group ranking, banded props). |
| `functions/api/` | `submit` (record an entry), `results` / `entry` (read for the leaderboard and shared views). |

## Run it locally

Front end only (quickest look, no backend):
```
python -m http.server 8080      # then open http://localhost:8080
```

Full stack (site + API + a local D1) uses Cloudflare's Wrangler. Setup, local dev, deploy,
secrets, the daily score-update workflow, and the DB schema live in **[BACKEND.md](BACKEND.md)**
and **`schema.sql`**.

## Data pipeline (`scrape.py`)
Writes the JSON the site reads into `./data/`. Requires Python 3.10+.

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python scrape.py --verbose
```

Per step (each writes one file):

| Step | Output | Source |
|------|--------|--------|
| `--only groups` | `groups.json` | Wikipedia (tournament page) |
| `--only rosters` | `rosters.json` | Wikipedia (squads page) |
| `--only photos --squads-html PATH` | adds `photo` to `rosters.json` | Wikipedia `pageimages` API (~75% coverage) |
| `--only rankings --rankings-html PATH` | FIFA ranks into `teams.json` | a saved FIFA rankings page |
| `--only form` | `form.json` | international-football.net (last 10 games) |
| `--only schedule --schedule-txt PATH` | `schedule.json` | a text schedule |
| `--only results --results-txt PATH` | `live.json` (group standings) | a text file of played scores |

Team names are normalized via `TEAM_ALIASES` so every file keys on the same string.

## Notes
- `data/answer_key.json` is host-maintained. Fill in real outcomes as they happen and the
  leaderboard scores everyone automatically.
- `archive/` (git-ignored) holds the original spec and the schedule source, for reference.
