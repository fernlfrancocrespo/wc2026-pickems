# 🏁 Conclusion Plan — knockout stage → final grading → wind-down

The road from today (July 2) to crowning a winner. Companion to `SUNDAY_RUNBOOK.md`
(which covers the email machinery). Run everything from the project folder in Git Bash.

---

## 📍 Where things stand (July 2)

- ✅ Group stage complete (72 matches), tables final, R32 fully populated (16/16).
- ✅ 61 entries in D1; bracket window closed June 29 — everything is now read-only for players.
- ✅ `data/bracket_state.json` has all **10 decided R32 results** (through July 1's USA and
  Belgium wins). Still to play: M83 Portugal–Croatia, M84 Spain–Austria, M85 Switzerland–Algeria
  (tonight, July 2) and M86 Argentina–Cape Verde, M87 Colombia–Ghana, M88 Australia–Egypt (July 3).
- ✅ Live stat tallies current through July 1: 241 tournament goals, 2 shootouts, 3 extra-time
  matches, 27 added-time goals, longest goal 31.23m (Pina), Golden Boot Messi/Mbappé 6.
- ✅ `answer_key.json`: q10 = Yes (hat-tricks happened — settled). Everything else null,
  with the fill-by dates below.
- ✅ standings.html now shows the real bracket + the Pick-'Ems Pulse (champion picks
  alive/out, field consensus on undecided games).

## 🗓️ Tournament calendar (what triggers work)

| Round | Dates | Site work |
|---|---|---|
| Round of 32 | Jun 28 – Jul 3 | update results after each matchday |
| Round of 16 | Jul 4 – Jul 7 | same |
| Quarter-finals | Jul 9 – Jul 11 | same |
| Semi-finals | Jul 14 – Jul 15 | same + fill q3a/q3b (losing semifinalists) |
| Third-place game | Jul 18 | nothing scored (bracket has no M103 — intentional) |
| **Final** | **Jul 19** | fill everything, final deploy, winner email |

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

1. Enter the final's result in `results_source.txt` + fill `q1, q2, q11–q16, q17–q22`.
2. Set `"final": true` and `"updated"` in `answer_key.json`.
3. `./deploy.sh --cards` → regenerates the 61 cards/packets with **final** standings.
4. Verify: leaderboard total for the top entry matches `run-eval.js` output
   (`node run-eval.js` cross-checks scoring); no `results_warnings` in `bracket_state.json`.
5. Send the finale emails (SUNDAY_RUNBOOK.md § Send the emails) — winner + percentile
   tiers are automatic. Announce the champion in the group chats.
6. Prize handoff per whatever you promised. 🎉

## 📦 Wind-down (week after the final)

1. Export D1 one last time (runbook Step 1 command) → keep `data/private/_raw_export.json`.
2. Freeze the site: everything is already read-only post-lock; optionally set
   `MAX_SUBMISSIONS=0` so no stray writes are possible.
3. Tag the repo: `git tag wc2026-final && git push --tags`.
4. Decide the domain's fate (wc2026-pickems.com renews in 2027 — let lapse or keep as
   a trophy page). The Pages site itself is free to leave up as a museum.
5. Optional: strip emails from D1 (`UPDATE submissions SET email=NULL;`) once the
   prize is settled — nothing on the site needs them after the last send.

## 🆘 Same failure modes as always

Scrape flaky → wait + retry or `--no-scrape`; API blip → redeploy pins `wrangler.toml`;
score disputes → `node run-eval.js` is the referee; lost links → `_mailmerge.csv`.
