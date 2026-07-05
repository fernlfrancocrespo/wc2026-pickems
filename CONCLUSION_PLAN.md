# 🏁 Conclusion Plan — knockout stage → final grading → wind-down

The road to crowning a winner. Run everything from the project folder in Git Bash.

> **7/5 pivot: no more emails.** The percentile-card email machinery (SUNDAY_RUNBOOK.md,
> `build_email_cards.py`, `--cards`) is retired — kept in the repo for history only.
> The site is now fully self-serve: every page refreshes itself as results land, and
> **/finale.html** is the closer — it runs in PREVIEW mode today and becomes the official
> celebration page the moment `answer_key.json` gets `"final": true` (the leaderboard and
> home hub start linking to it automatically at the same moment).

## 📍 Where things stand (July 5)

- ✅ Group stage complete (72 matches); 61 entries; everything read-only for players.
- ✅ R32 complete (16/16 results in `bracket_state.json`); R16 underway — France (M89)
  and Morocco (M90) through. Still to play: M91 Brazil–Norway, M92 Mexico–England (today),
  M93–96 (Jul 6–7).
- ✅ Live tallies current through M90: 261 tournament goals, 3 shootouts, 5 extra-time
  matches, 28 added-time goals, longest goal 31.23m (Pina), Golden Boot Messi/Mbappé 7.
- ✅ `answer_key.json`: q10 = Yes. Everything else null, with the fill-by dates below.
- ✅ Pages: standings.html (bracket + pulse), leaderboard.html (live ranking),
  finale.html (podium/honors/full-field — preview mode until the final).

## 🗓️ Tournament calendar (what triggers work)

| Round | Dates | Site work |
|---|---|---|
| Round of 32 | Jun 28 – Jul 3 | update results after each matchday |
| Round of 16 | Jul 4 – Jul 7 | same |
| Quarter-finals | Jul 9 – Jul 11 | same |
| Semi-finals | Jul 14 – Jul 15 | same + fill q3a/q3b (losing semifinalists) |
| Third-place game | Jul 18 | nothing scored (bracket has no M103 — intentional) |
| **Final** | **Jul 19** | fill everything, flip `"final": true`, final deploy — finale.html goes official |

## 🔁 After every knockout matchday (~10 min)

1. `python populate_bracket.py` — scrapes the Wikipedia knockout page and refreshes
   `bracket_state.json` results (winners, shootouts included) automatically.
   (`results_source.txt` is group-stage only — never add knockout games there.)
2. Update the **manual knockout tallies** in `data/live_stats.json` from the day's
   match reports: `tournament_goals_total`, `penalty_shootouts`, `extra_time_matches`,
   `goal_timing.goals_counted` / `added_time_goals` (+ `fastest_goal_seconds` if beaten),
   `matches_played`, and knockout goals in `top_scorers`. Check `ball_stats.json` if a
   long-range screamer beat 31.23m.
3. `./deploy.sh --no-scrape` — regrades brackets + leaderboard, deploys. (Skip the
   group scraper: groups are final and a re-run would regress the manual knockout tallies.)
4. Sanity check: standings.html bracket shows the winners green; leaderboard order moved.

> The bracket auto-grades from `bracket_state.json`; q9/q10/q8 are settled; q11–q16 and
> the Golden Boot show as LIVE projections from the tallies in step 2. Only the answers
> below need typing by hand when they become final.

## ✍️ Answer-key fill-in schedule (`data/answer_key.json`)

Fill each value as it becomes true, then `./deploy.sh --no-scrape`:

| Key | Question | Fill when |
|---|---|---|
| `q3a`, `q3b` | losing semifinalists | after SF2 (Jul 15) |
| `q2` | runner-up | after the final |
| `q1` | champion | after the final |
| `q4` | best host nation | after hosts' last elimination (may be earlier!) |
| `q5` / `q6` | best CAF / AFC team | when the last CAF/AFC team is out |
| `q7` | Cinderella | your judgment call once its run ends |
| `q11–q16` | tournament-total props | after the final (running tallies in `live_stats.json` / `ball_stats.json`) |
| `q17–q22` | player awards (`*_player` keys) | FIFA announces Golden Ball/Boot/Glove + Young Player right after the final; q21 (scores in final) & q22 (post-group goals) from the match itself |

Watch `q4/q5/q6` — they can settle mid-knockouts (e.g. last AFC team eliminated in the R16).
Filling them early keeps the leaderboard honest and the group chat noisy.

## 🏆 Final day (July 19) — closing checklist

1. `python populate_bracket.py` for the final's result + fill `q1, q2, q11–q16, q17–q22`
   in `answer_key.json` (final knockout tallies in `live_stats.json` too).
2. Set `"final": true` and `"updated"` in `answer_key.json`. **This one flag is the switch:**
   finale.html drops its preview banner, gets confetti, reveals "Called the champion,"
   and the leaderboard + home hub start linking to it.
3. `./deploy.sh --no-scrape`.
4. Verify: finale.html podium matches `node run-eval.js` output (the scoring referee);
   no `results_warnings` in `bracket_state.json`.
5. Drop the link in the group chats: **wc2026-pickems.com/finale.html**. That's the
   announcement — no emails.
6. Prize handoff per whatever you promised. 🎉

## 📦 Wind-down (week after the final)

1. Export D1 one last time (runbook Step 1 command) → keep `data/private/_raw_export.json`.
2. Freeze the site: everything is already read-only post-lock; optionally set
   `MAX_SUBMISSIONS=0` so no stray writes are possible.
3. Tag the repo: `git tag wc2026-final && git push --tags`.
4. Decide the domain's fate (wc2026-pickems.com renews in 2027 — let lapse or keep as
   a trophy page). The Pages site itself is free to leave up as a museum.
5. Optional: strip emails from D1 (`UPDATE submissions SET email=NULL;`) once the
   prize is settled — with the email plan retired, nothing needs them at all.

## 🆘 Same failure modes as always

Scrape flaky → wait + retry or `--no-scrape`; API blip → redeploy pins `wrangler.toml`;
score disputes → `node run-eval.js` is the referee.
