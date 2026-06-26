# 🌅 Sunday Runbook — sending the bracket emails

Everything you need to refresh the site to final group-stage results and send the 61
bracket emails. Run these from the project folder in **Git Bash** (or your terminal):
`D:\Documents\Personal Docs\AI\World-cup-Pickems-index`

---

## ✅ One-time (do this once, any time before Sunday)
1. Open `build_email_cards.py`, set your tutorial video links near the top:
   ```python
   TUTORIAL_EN = "https://your-english-tutorial"
   TUTORIAL_PT = "https://seu-tutorial-em-portugues"
   ```
2. Make sure `data/bracket.json` says `"open": true` (it already is). To CLOSE the
   bracket later, set it to `false` and run `./deploy.sh --no-scrape`.

---

## 🚀 Sunday morning — 2 commands

### Step 1 — pull the current entries (gets each person's data + secret edit token)
```bash
npx wrangler d1 execute wc2026 --remote --json \
  --command "SELECT id, created_at, slug, name, display_name, email, country, lang, payload, edit_token FROM submissions ORDER BY created_at ASC" \
  > data/private/_raw_export.json
```

### Step 2 — scrape final results, build the bracket, regenerate emails, deploy
```bash
./deploy.sh --cards
```
This scrapes the finished groups (Wikipedia + ESPN cross-check), populates the **final**
Round-of-32 teams, re-scores everyone, rebuilds all 61 cards + email packets, and pushes
to production.

**Check the output says:** `group_stage_complete: True`, all 12 groups complete,
`R32 matches fully populated: 16/16`, and `VALIDATION … clean [OK]`.

---

## 📧 Send the emails
Files are in **`out/email_packets/<rank>_<handle>.txt`** (and `out/email_cards/_mailmerge.csv`).
Each `.txt` has:
- `TO:` their email
- `SUBJECT:` (personalized)
- `ATTACH:` which card image to attach (from `out/email_cards/`)
- the body (their secret bracket link is already in it)

Tone is automatic by how they're doing: top contenders get "you're in the mix," the
field gets "anyone can win," and lower entries get pure celebration (no rank/field
shown). Portuguese is auto-selected for the family. Just paste subject + body into
Gmail, attach the matching card, send.

> Prefer a spreadsheet? Open `out/email_cards/_mailmerge.csv` — it has `subject`, `body`,
> `card_file`, and `link` columns for copy-paste or mail-merge (YAMM etc.).

---

## 🔁 Re-running later (after each matchday)
Just `./deploy.sh --cards` again (re-do Step 1 first if anyone's entry changed). It
re-scrapes, re-scores, and redeploys. The bracket auto-grades itself as knockout games
are played.

---

## 🆘 If something breaks
- **Leaderboard / `/p/` shows "No entries yet":** the API binding blipped. Re-run
  `./deploy.sh --no-scrape` (it always stages `wrangler.toml`, which pins the DB binding).
  Confirm with: `curl -s https://wc2026-pickems.com/api/results | head -c 60` → should
  start `{"ok":true,"count":61`.
- **`deploy.sh` fails on the scrape:** Wikipedia may be mid-edit. Wait a few minutes and
  retry, or run `./deploy.sh --no-scrape` to deploy without re-scraping.
- **Validation warning (scores don't reconcile):** don't trust the numbers — re-run the
  scrape once; if it persists, ping me with the warning text.
- **Someone says their link doesn't work / lost it:** find them in
  `out/email_cards/_mailmerge.csv`, resend the `link` column (it has their token).
- **Wrong person's email / want to resend one:** their tokened link is the `link` column
  in the CSV.

---

## 📌 Notes
- Group/award/champion outcomes (q1–q7, q17–q22) are **host-entered** in
  `data/answer_key.json` as they happen — fill the value, leave unknowns `null`, then
  `./deploy.sh --no-scrape`. (q8/q9/q10 and the bracket grade automatically.)
- The bracket is a bonus on top of the main 251-point game; SF/final kept small on
  purpose since champion/runner-up/semifinalists are already scored.
