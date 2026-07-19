# 🏁 Final-Day Closeout — do this yourself, no AI needed

This is the **complete, self-contained** checklist to finish the pool after the third-place
game (Jul 18) and the final (Jul 19). Everything is: edit a JSON file in a text editor, then
run one or two commands in **Git Bash** from the project folder. No Claude required.

**The two commands you'll ever run:**
```bash
./deploy.sh --no-scrape      # regrade every entry + push the site live (Cloudflare)
node run-eval.js             # the "referee" — prints the standings so you can sanity-check
```
`--no-scrape` is important: it skips the group scraper so your hand-typed knockout tallies
don't get wiped. If `deploy.sh` ever asks you to log in, that's **Cloudflare** (you own the
account) — log in and re-run.

**Where the site reads its truth from (only these files matter now):**
| File | Holds |
|---|---|
| `data/answer_key.json` | The official answers. **`"final": true` here is the master switch.** |
| `data/bracket_state.json` | Knockout winners (`results`) + scores (`scores`). |
| `data/live_stats.json` | Tournament tallies (goals, shootouts, ET, top scorers). |
| `data/ball_stats.json` | Longest-range goal (q15) — the only stat with no feed. |

Team names and player names you type **must be spelled exactly** as they appear elsewhere in
the data (accents included: `Kylian Mbappé`, `Lautaro Martínez`). A misspelling just scores
everyone 0 on that question. When unsure, copy the spelling from `data/live_stats.json`'s
`top_scorers` list or from `data/results_source.txt`.

---

## STEP 1 — Third-place game (July 18, France vs England). Tallies only.

The third-place game earns **zero pick-em points** (by design — it's not in the bracket). It
matters *only* because its goals count toward tournament totals and the top-scorer race. So:

1. Open **`data/live_stats.json`**. Watch the match and update these numbers by adding what
   happened in the 3rd-place game:
   - `matches_played` → **+1** (becomes 103).
   - `tournament_goals_total` → add the total goals in the match.
   - `goal_timing.goals_counted` → same number, keep it equal to `tournament_goals_total`.
   - `goal_timing.added_time_goals` → **+1 for each goal** whose minute is shown as `90+x`
     (or `120+x`). Normal-time goals don't count here.
   - `penalty_shootouts` → **+1** only if it went to a shootout.
   - `extra_time_matches` → **+1** only if it went to extra time.
   - `top_scorers` → for any player who scored, bump their `goals` (or add them at the bottom
     if they aren't listed and now have 3+; the list is a top-scorers board).
2. If a goal was struck from farther than **31.23 m** (the current record, Kevin Pina), open
   **`data/ball_stats.json`** and update `q15_longest_range_m` + add a row to
   `longest_range_goals`. Otherwise leave it alone.
3. If a goal was faster than **64.0 seconds**, update `goal_timing.fastest_goal_seconds`.
   Otherwise leave it.
4. Save, then:
   ```bash
   ./deploy.sh --no-scrape
   ```
   You don't have to do this step on the 18th if you'd rather batch it — you can fold the
   third-place numbers into the final push on the 19th. Just don't forget them.

---

## STEP 2 — The Final (July 19, Spain vs Argentina). The real closeout.

Watch the match, note the scorers and minutes, then do the following **in order**.

### 2a. Record the final result in the bracket

Open **`data/bracket_state.json`**.

- In the **`results`** block, after the `"102"` line, add the champion. Match 104 is the final;
  `s1` is the SF1 winner (**Spain**), `s2` is the SF2 winner (**Argentina**):
  ```json
      "102": "Argentina",
      "104": "<the winner — Spain or Argentina>"
  ```
- In the **`scores`** block, after the `"102"` entry, add the final score. `s1` = Spain's goals,
  `s2` = Argentina's goals (regulation + ET; if it went to penalties, add a `pens` object too,
  same shape as match `74` earlier in the file):
  ```json
      "102": { "s1": 1, "s2": 2 },
      "104": { "s1": <Spain goals>, "s2": <Argentina goals> }
  ```
- Bump `"updated"` at the top to today's date (any value; it's just a timestamp).

> There is intentionally **no match 103** in the bracket — the third-place game is never scored.
> Don't add one.

*(Optional shortcut instead of hand-typing the winner: run
`PYTHONIOENCODING=utf-8 ./venv/Scripts/python.exe populate_bracket.py`. It scrapes Wikipedia's
knockout page and fills `results["104"]` automatically once Wikipedia posts the result, and it
will **not** erase anything already recorded. You still add the `scores["104"]` line by hand.
If Wikipedia hasn't updated yet, just hand-type the winner as above.)*

### 2b. Fill the answer key

Open **`data/answer_key.json`**. Fill each `null`. Reminder: **q11–q16 want the raw final
number** (the site converts it to the right band and awards full/half automatically).

| Key | What to enter | Example |
|---|---|---|
| `q1` | Champion (team name) | `"Spain"` |
| `q2` | Runner-up / beaten finalist | `"Argentina"` |
| `q9` | Total **group-stage** goals — already known: **215** | `215` |
| `q11` | Total goals, **whole tournament** (your final `tournament_goals_total`) | `305` |
| `q12` | Total knockout shootouts (your final `penalty_shootouts`) | `4` |
| `q13` | Total knockout matches that went to extra time (`extra_time_matches`) | `8` |
| `q14` | Total added-time goals (`goal_timing.added_time_goals`) | `34` |
| `q15` | Longest-range goal in **meters** (from `ball_stats.json`) | `31.23` |
| `q16` | Fastest goal in **seconds** (`goal_timing.fastest_goal_seconds`) | `64.0` |
| `q17_player` | **Golden Ball** winner — FIFA announces right after the final | `"Lamine Yamal"` |
| `q18_player` | **Golden Boot** (top scorer) — FIFA announces | `"Kylian Mbappé"` |
| `q19_player` | **Young Player** of the tournament — FIFA announces | `"..."` |
| `q20_player` | **Golden Glove** (best keeper) — FIFA announces | `"Unai Simón"` |
| `q21_player` | **Every player who scored in the final** — as a list (see below) | `["Oyarzabal","Messi"]` |
| `q22_player` | Most goals **after the group stage** — a name, or a list if tied | `["Kylian Mbappé","Jude Bellingham"]` |

- **q21 is a list on purpose.** The question is "any player to score in the final," so put
  *every* final scorer in an array — anyone who picked any of them is correct:
  ```json
      "q21_player": ["Mikel Oyarzabal", "Lionel Messi"],
  ```
- **q22** — count knockout-stage goals per player from your `top_scorers` work. Right now the
  leaders are Mbappé 4 and Bellingham 4 (both already eliminated), Oyarzabal 3. If the final
  changes the top, update accordingly; if there's a tie, use an array.
- `q8` can stay `{}` — the final group tables in `live_stats.json` already drive it.
- `q3a`/`q3b` (France, England), `q4`–`q7` are already filled and correct. Leave them.
- Bump `"updated"` to today.

### 2c. Finalize the tallies

Open **`data/live_stats.json`** and fold in the final's numbers exactly like Step 1 (goals,
added-time goals, a shootout/ET if it happened, top scorers). Make `tournament_goals_total`
and `goal_timing.goals_counted` match each other and match what you put in `q11`.

### 2d. Flip the master switch

Back in **`data/answer_key.json`**, change:
```json
  "final": false,
```
to:
```json
  "final": true,
```
This one line drops the preview banner on `finale.html`, turns on the confetti, reveals the
"Called the champion" honor, and makes the leaderboard + home page start linking to the finale
page.

### 2e. Deploy and verify

```bash
./deploy.sh --no-scrape
node run-eval.js
```
- `run-eval.js` prints the final standings — this is your referee. The **#1 name it prints is
  your champion.** Confirm it looks sane (the winner should have jumped on champion/final points).
- Open **https://wc2026-pickems.com/finale.html** — you should see confetti, the champion name
  in the hero, the podium of the top 3 players, the honors cards (including "Called the champion"),
  and the full field. No yellow "preview" banner.
- Open **https://wc2026-pickems.com/standings.html** — the bracket should show the champion in
  the FINAL slot, in green.

That's the pool crowned. Share the link: **wc2026-pickems.com/finale.html**

---

## STEP 3 — Wind-down (any time in the week after)

None of this is urgent; the site is already read-only for players and will sit fine as-is.

1. **Tag the repo** so this state is preserved:
   ```bash
   git add -A
   git commit -m "Final: <champion> champions. Pool closed."
   git tag wc2026-final
   git push && git push --tags
   ```
2. **Merge to main if you want the primary branch to reflect the finish** (you've been working
   on `scored-entry-overlay`, which is also the preview branch). Optional — the live site is
   already deployed regardless of branch.
3. **Cloudflare / domain:** `wc2026-pickems.com` renews in 2027. Do nothing and it stays up as
   a trophy page until then; let it lapse if you don't want to pay. The Pages hosting is free to
   leave running.
4. **Subscription:** nothing in this project depends on Claude. Once the above is deployed, you
   never need to touch it again.

---

## If something looks wrong

- **A player-award question scored everyone 0** → almost always a name-spelling mismatch. Copy
  the exact spelling from `live_stats.json` `top_scorers` or `results_source.txt`.
- **The bracket didn't update** → check `data/bracket_state.json` actually has your `"104"` line
  in both `results` and `scores`, that it's valid JSON (commas in the right places), and that you
  ran `./deploy.sh --no-scrape` afterward.
- **The site still shows the preview banner** → `"final"` is still `false`, or the deploy didn't
  finish. Re-run `./deploy.sh --no-scrape`.
- **JSON error / site blank** → you likely dropped a comma or quote. Paste the file into any
  "JSON validator" website to find the bad line, fix, redeploy.
- **`run-eval.js` is the source of truth** for scoring disputes — whatever it prints is what the
  site shows.
