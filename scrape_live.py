#!/usr/bin/env python
"""
scrape_live.py — pull live group-stage results from Wikipedia's 12 per-group pages
and write the data the leaderboard/standings pages read.

    python scrape_live.py [--verbose]

Source: https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_<A..L>
Each page has, independently maintained on the same page:
  • "footballbox" divs    — individual match scores (our result lines)
  • the standings table   — Pos / Pld / W / D / L / GF / GA / GD / Pts

We parse BOTH and reconcile them: standings rebuilt from the match scores must
equal the page's own standings table. A mismatch means a parse error or a page
mid-edit, and is reported (never silently written). This is the within-Wikipedia
validation; an external FotMob cross-check is layered on separately.

Outputs (all under data/):
  results_source.txt   auto-generated played-match lines (Home G-G Away)
  live.json            group standings (via scrape.build_live_standings)
  live_stats.json      trending answer-key context: provisional group order (q8),
                       group-stage goals so far (q9), per-group completion, and the
                       validation report.
"""
from __future__ import annotations
import argparse
import re
import sys
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# Reuse the canonical helpers/data from the main scraper (import-safe: main-guarded).
from scrape import (
    DATA_DIR, HEADERS, normalize, build_live_standings, write_json,
)
import json

WIKI_GROUP_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_Group_{letter}"
SCORE_RE = re.compile(r"(\d+)\s*[–\-:]\s*(\d+)")          # 2–0 / 2-0 / 2:0
INT_RE   = re.compile(r"-?\d+")                            # ints incl. negative GD


def log(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(msg, file=sys.stderr)


def load_groups() -> dict[str, list[str]]:
    with open(DATA_DIR / "groups.json", encoding="utf-8") as f:
        return json.load(f)


def fetch(url: str, verbose: bool) -> str:
    for attempt in range(4):
        r = requests.get(url, headers=HEADERS, timeout=30)
        if r.status_code == 429:
            wait = 2 ** (attempt + 1)
            log(f"  429 → waiting {wait}s", verbose)
            time.sleep(wait)
            continue
        r.raise_for_status()
        return r.text
    r.raise_for_status()
    return ""


def resolve_team(raw: str, teams: list[str]) -> str | None:
    """Map a cell's raw text to one of this group's canonical team names.

    Cells carry annotations Wikipedia adds: "(H, A)" host/advanced markers, an
    "v t e" edit-link, flag alt text. Strip those, then normalize (which also
    maps aliases like Turkey→Türkiye, Czech Republic→Czechia)."""
    clean = re.sub(r"\(.*?\)", "", raw)          # drop "(H, A)" / "(E)" markers
    clean = re.sub(r"\bv\s*t\s*e\b", "", clean, flags=re.I).strip()
    n = normalize(clean)
    if n in teams:
        return n
    # token/substring fallback against canonical names AND their aliases
    low = clean.lower()
    for t in teams:
        if t.lower() in low:
            return t
    from scrape import TEAM_ALIASES
    for alias, canon in TEAM_ALIASES.items():
        if canon in teams and alias.lower() in low:
            return canon
    return None


def parse_matches(soup: BeautifulSoup, teams: list[str], verbose: bool) -> list[dict]:
    """Played matches from footballbox divs → [{home, away, hs, as}]."""
    out = []
    for box in soup.select("div.footballbox"):
        h = box.select_one(".fhome"); s = box.select_one(".fscore"); a = box.select_one(".faway")
        if not (h and s and a):
            continue
        m = SCORE_RE.search(s.get_text(strip=True))
        if not m:
            continue  # unplayed ("Match NN")
        home = resolve_team(h.get_text(" ", strip=True), teams)
        away = resolve_team(a.get_text(" ", strip=True), teams)
        if not home or not away:
            log(f"  [match] unresolved team: {h.get_text(strip=True)!r} vs {a.get_text(strip=True)!r}", verbose)
            continue
        out.append({"home": home, "away": away, "hs": int(m.group(1)), "as": int(m.group(2))})
    return out


def parse_scorers(soup: BeautifulSoup, teams: list[str], verbose: bool) -> list[dict]:
    """Goalscorers per played match from footballbox goal cells.
    Returns [{player, team, goals}] — own goals (o.g.) excluded; pens count."""
    out = []
    for box in soup.select("div.footballbox"):
        s = box.select_one(".fscore")
        if not (s and SCORE_RE.search(s.get_text(strip=True))):
            continue  # unplayed
        h = box.select_one(".fhome"); a = box.select_one(".faway")
        home = resolve_team(h.get_text(" ", strip=True), teams) if h else None
        away = resolve_team(a.get_text(" ", strip=True), teams) if a else None
        for cell_cls, team in ((".fhgoal", home), (".fagoal", away)):
            if not team:
                continue
            cell = box.select_one(cell_cls)
            if not cell:
                continue
            # Multiple scorers → one <li> each (plainlist); a single scorer sits bare
            # in the cell with no list, so fall back to the whole cell as one entry.
            for entry in (cell.select("li") or [cell]):
                link = entry.find("a", title=True)
                # full name, minus Wikipedia disambiguation like "(footballer, born 1999)"
                player = re.sub(r"\s*\(.*?\)\s*$", "",
                                (link.get("title") if link else entry.get_text(" ", strip=True))).strip()
                if not player:
                    continue
                # Goals = number of MINUTE markers (Wikipedia shows one ball icon per
                # scorer but lists each goal's minute, e.g. "Messi 17', 60', 76'" = 3).
                txt = entry.get_text(" ", strip=True)
                goals = len(re.findall(r"\d+\+?\d*['′]", txt))
                low = txt.lower()
                if "o.g." in low or "(og)" in low:
                    goals -= low.count("o.g.") + low.count("(og)")  # own goals don't count for scorer
                if goals > 0:
                    out.append({"player": player, "team": team, "goals": goals})
    return out


ADDED_TIME_RE = re.compile(r"(?:90|120)\+\d+\s*['′]")   # 90+x' or 120+x' (NOT 45+x)


def count_added_time_goals(soup: BeautifulSoup) -> int:
    """q14: goals scored after 90:00 or after 120:00. Counts '90+x' / '120+x' minute
    tokens in the goal cells of played matches (first-half 45+x stoppage excluded)."""
    n = 0
    for box in soup.select("div.footballbox"):
        s = box.select_one(".fscore")
        if not (s and SCORE_RE.search(s.get_text(strip=True))):
            continue
        for cls in (".fhgoal", ".fagoal"):
            cell = box.select_one(cls)
            if cell:
                n += len(ADDED_TIME_RE.findall(cell.get_text(" ", strip=True)))
    return n


def parse_standings_table(soup: BeautifulSoup, teams: list[str], verbose: bool) -> dict[str, dict]:
    """Page's own standings table → {team: {pld,w,d,l,gf,ga,gd,pts,pos}}."""
    target = None
    for t in soup.select("table.wikitable"):
        head = " ".join(th.get_text(strip=True) for th in t.select("th")[:12])
        if "Pld" in head and "Pts" in head and ("Pos" in head or "Team" in head):
            target = t
            break
    if target is None:
        return {}
    out = {}
    for row in target.select("tr"):
        cells = row.find_all(["td", "th"])
        if len(cells) < 9:
            continue
        team = None
        for c in cells:
            team = resolve_team(c.get_text(" ", strip=True), teams)
            if team:
                break
        if not team:
            continue
        nums = [int(x) for x in INT_RE.findall(row.get_text(" ", strip=True))]
        if len(nums) < 8:
            continue
        pld, w, d, l, gf, ga, gd, pts = nums[-8:]
        pos = nums[0] if nums[0] <= len(teams) else None
        out[team] = {"pld": pld, "w": w, "d": d, "l": l, "gf": gf, "ga": ga, "gd": gd, "pts": pts, "pos": pos}
    return out


def reconcile(letter: str, matches: list[dict], table: dict[str, dict], teams: list[str], verbose: bool) -> list[str]:
    """Rebuild standings from match scores; compare to the page's own table."""
    issues = []
    calc = {t: {"pld": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "pts": 0} for t in teams}
    for m in matches:
        for t, gf, ga in ((m["home"], m["hs"], m["as"]), (m["away"], m["as"], m["hs"])):
            c = calc[t]; c["pld"] += 1; c["gf"] += gf; c["ga"] += ga
            if gf > ga: c["w"] += 1; c["pts"] += 3
            elif gf == ga: c["d"] += 1; c["pts"] += 1
            else: c["l"] += 1
    for t in teams:
        if t not in table:
            issues.append(f"{letter}: '{t}' missing from standings table")
            continue
        for k in ("pld", "w", "d", "l", "gf", "ga", "pts"):
            if calc[t][k] != table[t][k]:
                issues.append(f"{letter}/{t}: {k} matches={calc[t][k]} table={table[t][k]}")
    return issues


ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world"


def fetch_espn_results(dates: list[str], teams_all: set[str], verbose: bool) -> tuple[dict, list[str]]:
    """External 2nd source: ESPN public scoreboard. Returns ({frozenset({home,away}):
    {home, away, hs, as}}, [event_ids]) for COMPLETED matches between two WC teams."""
    out: dict[frozenset, dict] = {}
    event_ids: list[str] = []
    for d in dates:
        try:
            r = requests.get(f"{ESPN_BASE}/scoreboard?dates={d}", headers=HEADERS, timeout=20)
            if r.status_code != 200:
                continue
            for e in r.json().get("events", []):
                comp = e.get("competitions", [{}])[0]
                if comp.get("status", e.get("status", {})).get("type", {}).get("state") != "post":
                    continue
                cs = comp.get("competitors", [])
                if len(cs) != 2:
                    continue
                sides = {}
                for c in cs:
                    name = normalize(c.get("team", {}).get("displayName", ""))
                    try: sides[name] = int(c.get("score"))
                    except (TypeError, ValueError): sides = {}; break
                names = [n for n in sides if n in teams_all]
                if len(names) != 2:
                    continue
                home = next((normalize(c["team"]["displayName"]) for c in cs if c.get("homeAway") == "home"), names[0])
                away = next((n for n in names if n != home), names[1])
                out[frozenset(names)] = {"home": home, "away": away, "hs": sides[home], "as": sides[away]}
                event_ids.append(e.get("id"))
        except Exception as ex:
            log(f"  [espn] {d}: {str(ex)[:80]}", verbose)
        time.sleep(0.2)
    return out, event_ids


REGULATION_END = 5400.0   # 90:00 in seconds
EXTRA_TIME_END = 7200.0   # 120:00 in seconds


def fetch_goal_timing(event_ids: list[str], verbose: bool) -> dict:
    """Per-match scoring keyEvents from ESPN summary → goal-timing props.
    clock.value is in SECONDS. Derives:
      q16 fastest goal  = min(seconds) across the tournament
      q14 added-time goals = count of goals scored AFTER 90:00 (or after 120:00 in
          ET) — i.e. end-of-period stoppage goals (NOT first-half stoppage)."""
    goals = []  # seconds for every goal
    added_time = 0
    for eid in event_ids:
        try:
            d = requests.get(f"{ESPN_BASE}/summary?event={eid}", headers=HEADERS, timeout=20).json()
        except Exception as ex:
            log(f"  [timing] {eid}: {str(ex)[:60]}", verbose); continue
        for ev in d.get("keyEvents", []):
            if not ev.get("scoringPlay"):
                continue
            secs = (ev.get("clock") or {}).get("value")
            if secs is None:
                continue
            goals.append(secs)
            # after 90:00 in regulation, or after 120:00 in extra time
            if secs > REGULATION_END or secs > EXTRA_TIME_END:
                added_time += 1
        time.sleep(0.15)
    if not goals:
        return {"goals_counted": 0}
    return {
        "goals_counted": len(goals),
        "fastest_goal_seconds": round(min(goals), 1),     # q16
        "added_time_goals": added_time,                    # q14 (group-stage subtotal so far)
    }


def cross_check_espn(wiki_matches: list[dict], espn: dict[frozenset, dict], verbose: bool) -> list[str]:
    """Compare each Wikipedia match score to ESPN's. Flag disagreements / missing."""
    issues = []
    for m in wiki_matches:
        key = frozenset({m["home"], m["away"]})
        e = espn.get(key)
        if not e:
            issues.append(f"ESPN missing: {m['home']} {m['hs']}-{m['as']} {m['away']}")
            continue
        # compare as {team:score} so home/away orientation doesn't matter
        wiki = {m["home"]: m["hs"], m["away"]: m["as"]}
        esp = {e["home"]: e["hs"], e["away"]: e["as"]}
        if wiki != esp:
            issues.append(f"SCORE DISAGREE {set(key)}: wiki={wiki} espn={esp}")
    return issues


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    V = args.verbose

    groups = load_groups()
    team_to_group = {t: L for L, ts in groups.items() for t in ts}

    all_matches: list[dict] = []
    all_issues: list[str] = []
    all_scorers: list[dict] = []
    per_group: dict[str, dict] = {}
    total_goals = 0
    added_time_total = 0

    for letter in sorted(groups):
        teams = groups[letter]
        url = WIKI_GROUP_URL.format(letter=letter)
        soup = BeautifulSoup(fetch(url, V), "html.parser")
        matches = parse_matches(soup, teams, V)
        table = parse_standings_table(soup, teams, V)
        issues = reconcile(letter, matches, table, teams, V)
        all_issues += issues
        all_matches += matches
        all_scorers += parse_scorers(soup, teams, V)
        total_goals += sum(m["hs"] + m["as"] for m in matches)
        added_time_total += count_added_time_goals(soup)

        # provisional order: trust the page's Pos when present, else points/gd/gf
        if table and all(v.get("pos") for v in table.values()):
            order = sorted(table, key=lambda t: table[t]["pos"])
        else:
            order = sorted(teams, key=lambda t: (-table.get(t, {}).get("pts", 0),
                                                 -table.get(t, {}).get("gd", 0),
                                                 -table.get(t, {}).get("gf", 0), t))
        per_group[letter] = {
            "provisional_order": order,
            "matches_played": len(matches),
            "complete": len(matches) >= 6,          # 4 teams → 6 group matches
            "standings": table,
        }
        log(f"  Group {letter}: {len(matches)} played, {len(issues)} issue(s)", True)

    # results_source.txt (generated) → live.json (reuse the canonical builder)
    header = ("# AUTO-GENERATED by scrape_live.py — do not edit by hand.\n"
              f"# Source: Wikipedia per-group pages. Updated {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n")
    lines = [f"{m['home']} {m['hs']}-{m['as']} {m['away']}" for m in all_matches]
    (DATA_DIR / "results_source.txt").write_text(header + "\n".join(lines) + "\n", encoding="utf-8")

    live = build_live_standings(groups, team_to_group, "\n".join(lines), verbose=V)
    write_json("live.json", live)

    # External 2nd source: cross-check every Wikipedia score against ESPN.
    dates = [f"202606{d:02d}" for d in range(11, 28)]   # group stage: Jun 11–27
    espn, event_ids = fetch_espn_results(dates, set(team_to_group), V)
    espn_issues = cross_check_espn(all_matches, espn, V)
    log(f"  [espn] {len(espn)} completed matches fetched, {len(espn_issues)} disagreement(s)", True)

    # Goal-timing props: fastest goal (q16) from ESPN seconds; added-time goals
    # (q14) from Wikipedia minute strings (ESPN clamps stoppage to 90:00).
    goal_timing = fetch_goal_timing(event_ids, V)
    goal_timing["added_time_goals"] = added_time_total
    log(f"  [timing] {goal_timing.get('goals_counted', 0)} goals; "
        f"fastest={goal_timing.get('fastest_goal_seconds')}s, "
        f"added-time goals={added_time_total}", True)

    # Golden Boot (q19 trending) + hat-tricks (q10). Tally goals per player across
    # matches; a single-match record with 3+ goals is a hat-trick.
    tally: dict[tuple, int] = {}
    hat_tricks = []
    for s in all_scorers:
        tally[(s["player"], s["team"])] = tally.get((s["player"], s["team"]), 0) + s["goals"]
        if s["goals"] >= 3:
            hat_tricks.append({"player": s["player"], "team": s["team"], "goals": s["goals"]})
    top_scorers = sorted(
        [{"player": p, "team": t, "goals": g} for (p, t), g in tally.items()],
        key=lambda x: (-x["goals"], x["player"]))[:15]
    log(f"  [scorers] {len(tally)} scorers, leader {top_scorers[0] if top_scorers else None}, "
        f"{len(hat_tricks)} hat-trick(s)", True)

    live_stats = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "wikipedia",
        "matches_played": len(all_matches),
        "group_goals_total": total_goals,           # q9 trending
        "top_scorers": top_scorers,                  # q19 Golden Boot trending
        "hat_trick_in_group_stage": len(hat_tricks) > 0,   # q10
        "hat_tricks": hat_tricks,
        "goal_timing": goal_timing,                  # q14 latest goal min, q16 fastest goal sec
        "group_stage_complete": all(g["complete"] for g in per_group.values()),
        "groups": per_group,                          # provisional q8 order per letter
        "validation": {
            "ok": not all_issues and not espn_issues,
            "wiki_internal": {"ok": not all_issues, "issues": all_issues},
            "espn_cross_check": {"ok": not espn_issues, "matches_compared": len(espn), "issues": espn_issues},
        },
    }
    write_json("live_stats.json", live_stats)

    print(f"\nlive: {len(all_matches)} matches, {total_goals} goals, "
          f"{'COMPLETE' if live_stats['group_stage_complete'] else 'in progress'}")
    all_problems = all_issues + espn_issues
    if all_problems:
        print(f"VALIDATION: {len(all_problems)} issue(s) — review before trusting:")
        for i in all_problems[:25]:
            print("  -", i)
    else:
        print(f"VALIDATION: Wikipedia internal reconcile + ESPN cross-check ({len(espn)} matches) both clean [OK]")


if __name__ == "__main__":
    main()
