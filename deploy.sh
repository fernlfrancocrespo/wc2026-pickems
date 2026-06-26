#!/usr/bin/env bash
# Refresh live data and deploy the site to Cloudflare Pages — one command.
#
#   ./deploy.sh                 refresh data (scrape+bracket) and deploy to PRODUCTION
#   ./deploy.sh --preview       same, but deploy to the preview branch
#   ./deploy.sh --no-scrape     deploy current files without re-scraping (code-only)
#   ./deploy.sh --cards         also regenerate the email cards (out/email_cards)
#
# Always stages a CLEAN copy: never uploads data/private/ or _preview_results.json.
# The bracket open/closed state is whatever data/bracket.json currently says — to
# open the bracket on June 27, set "open": true there first, then run this.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"; cd "$ROOT"
PY=./venv/Scripts/python.exe
BRANCH=main; SCRAPE=1; CARDS=0
for a in "$@"; do
  case "$a" in
    --preview)   BRANCH=scored-entry-overlay ;;
    --no-scrape) SCRAPE=0 ;;
    --cards)     CARDS=1 ;;
  esac
done

if [ "$SCRAPE" = "1" ]; then
  echo "▶ scraping live results + stats (FotMob/Wikipedia + ESPN cross-check)…"
  PYTHONIOENCODING=utf-8 "$PY" scrape_live.py
  echo "▶ populating bracket teams from standings…"
  PYTHONIOENCODING=utf-8 "$PY" populate_bracket.py
fi
if [ "$CARDS" = "1" ]; then
  echo "▶ regenerating email cards…"
  PYTHONIOENCODING=utf-8 node run-eval.js --project --json >/dev/null
  PYTHONIOENCODING=utf-8 "$PY" build_email_cards.py
fi

STAGE="$(mktemp -d)"; mkdir -p "$STAGE/data"
cp index.html leaderboard.html standings.html faq.html i18n.js scoring.js _redirects wrangler.toml "$STAGE/"
cp -r functions "$STAGE/"
cp data/*.json "$STAGE/data/" 2>/dev/null || true
rm -f "$STAGE/data/_preview_results.json"
# safety: never ship private participant data
if [ -d "$STAGE/data/private" ] || [ -f "$STAGE/data/_preview_results.json" ]; then
  echo "✗ ABORT: sensitive files in stage"; rm -rf "$STAGE"; exit 1
fi

OPEN="$(grep -o '"open":[^,]*' data/bracket.json)"
echo "▶ deploying to branch=$BRANCH  (bracket $OPEN)"
( cd "$STAGE" && npx wrangler pages deploy . --project-name wc2026-pickems --branch "$BRANCH" --commit-dirty=true )
rm -rf "$STAGE"
echo "✓ done"
[ "$BRANCH" = "main" ] && echo "  live: https://wc2026-pickems.com" || echo "  preview: https://scored-entry-overlay.wc2026-pickems.pages.dev"
