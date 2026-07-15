#!/usr/bin/env python
"""
populate_bracket.py — resolve real teams into the Round-of-32 bracket slots from
the current group standings + FIFA's third-place allocation table.

    python populate_bracket.py [--verbose]

Reads:  data/live.json (standings), data/bracket.json (structure),
        data/third_place_allocation.json, data/live_stats.json (completion flag)
Writes: data/bracket_state.json — R32 slot teams + qualifying third-place groups.
        Marked provisional until the group stage is complete; re-run at lock for
        the final bracket. Knockout results get added to this file as they play.
"""
import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"
KO_URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage"
SCORE_RE = re.compile(r"(\d+)\s*[–\-:]\s*(\d+)")


def scrape_knockout_results(bracket, r32_teams, all_teams):
    """Completed knockout match winners from Wikipedia → {match#: winner}. Maps by
    team-set, resolving round by round (R32 teams known; later rounds = prior winners).
    Penalty wins read from a '(x–y)' shootout score when regulation is level. Anything
    ambiguous is left ungraded + flagged. Returns ({match#: winner}, [warnings])."""
    try:
        import requests
        from bs4 import BeautifulSoup
        from scrape import HEADERS, normalize
    except Exception as e:
        return {}, [f"knockout scrape skipped: {e}"]

    def resolve(raw):
        n = normalize(re.sub(r"\(.*?\)", "", raw).strip())
        if n in all_teams:
            return n
        for t in all_teams:
            if t.lower() in raw.lower():
                return t
        return None

    by_pair, warnings = {}, []
    try:
        soup = BeautifulSoup(requests.get(KO_URL, headers=HEADERS, timeout=30).text, "html.parser")
    except Exception as e:
        return {}, [f"knockout fetch failed: {e}"]
    for box in soup.select("div.footballbox"):
        s = box.select_one(".fscore")
        if not s:
            continue
        m = SCORE_RE.search(s.get_text(strip=True))
        if not m:
            continue  # not played yet ("Match NN")
        h = box.select_one(".fhome"); a = box.select_one(".faway")
        home = resolve(h.get_text(" ", strip=True)) if h else None
        away = resolve(a.get_text(" ", strip=True)) if a else None
        if not home or not away:
            continue
        hs, as_ = int(m.group(1)), int(m.group(2))
        if hs > as_:
            win = home
        elif as_ > hs:
            win = away
        else:  # level after regulation/ET → look for a penalty shootout score
            txt = box.get_text(" ", strip=True)
            pm = re.search(r"\(\s*(\d+)\s*[–\-]\s*(\d+)\s*\)", txt)
            if not pm and "Penalties" in txt:
                # footballbox pens: bare "3–4" score cell after the "Penalties" header
                pm = re.search(r"(\d+)\s*[–\-]\s*(\d+)", txt[txt.find("Penalties"):])
            if not pm:
                warnings.append(f"undetermined winner: {home} {hs}-{as_} {away} (no pen score found)")
                continue
            win = home if int(pm.group(1)) > int(pm.group(2)) else away
        by_pair[frozenset({home, away})] = win

    # resolve match numbers by walking the bracket (ascending: feeders settle first)
    results = {}
    for mid in sorted(bracket["matches"], key=int):
        mm = bracket["matches"][mid]
        if mm["round"] == "R32":
            r = r32_teams.get(mid, {}); t1, t2 = r.get("s1"), r.get("s2")
        else:
            t1 = results.get(str(mm["s1"].get("m"))); t2 = results.get(str(mm["s2"].get("m")))
        if t1 and t2:
            w = by_pair.get(frozenset({t1, t2}))
            if w:
                results[mid] = w
    return results, warnings


def load(name):
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    live = load("live.json")
    bracket = load("bracket.json")
    alloc_table = load("third_place_allocation.json")
    try:
        complete = bool(load("live_stats.json").get("group_stage_complete"))
    except Exception:
        complete = False

    # Per-group winner / runner-up / third (live.json rows are pre-sorted by pts,gd,gf).
    standings = live.get("groups", {})
    pos = {}  # group -> {"W":team, "RU":team, "3rd": row}
    thirds = []
    for g, rows in standings.items():
        if len(rows) < 3:
            continue
        pos[g] = {"W": rows[0]["team"], "RU": rows[1]["team"], "3rd": rows[2]["team"]}
        thirds.append({"group": g, **rows[2]})

    # Eight best third-placed teams (FIFA tiebreakers: pts, gd, gf; name as deterministic last resort).
    thirds.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
    qualifying = sorted(t["group"] for t in thirds[:8])
    key = "".join(qualifying)
    alloc = alloc_table.get(key)  # {match#(str): group letter}

    def resolve(slot):
        if slot["t"] == "W":
            return pos.get(slot["g"], {}).get("W")
        if slot["t"] == "RU":
            return pos.get(slot["g"], {}).get("RU")
        if slot["t"] == "3rd":
            return None  # filled below from the allocation
        return None

    r32_teams = {}
    for mid, m in bracket["matches"].items():
        if m["round"] != "R32":
            continue
        s1, s2 = m["s1"], m["s2"]
        t1 = resolve(s1)
        t2 = resolve(s2)
        # third-place slot → group assigned to THIS match by the allocation table
        for slot, setter in ((s1, "t1"), (s2, "t2")):
            if slot["t"] == "3rd" and alloc and mid in alloc:
                team = pos.get(alloc[mid], {}).get("3rd")
                if setter == "t1":
                    t1 = team
                else:
                    t2 = team
        r32_teams[mid] = {"s1": t1, "s2": t2}

    # Knockout results (auto-grades the bracket once games are played; empty until then).
    all_teams = {t for ts in load("groups.json").values() for t in ts}
    ko_results, ko_warnings = scrape_knockout_results(bracket, r32_teams, all_teams)

    # The scrape may only ADD to what's already recorded — a flaky/partial page must
    # never erase known winners, and the hand-maintained scores block rides along.
    try:
        prev = load("bracket_state.json")
    except Exception:
        prev = {}
    for mid, w in prev.get("results", {}).items():
        if ko_results.get(mid, w) != w:
            ko_warnings.append(f"M{mid}: scrape says {ko_results[mid]}, keeping recorded {w} (resolve by hand)")
        ko_results[mid] = w
    ko_results = {mid: ko_results[mid] for mid in sorted(ko_results, key=int)}

    state = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provisional": not complete,
        "group_stage_complete": complete,
        "qualifying_third_groups": qualifying,
        "allocation_found": alloc is not None,
        "r32_teams": r32_teams,
        "results": ko_results,           # match# -> winning team (filled as knockouts play)
        "results_warnings": ko_warnings,
    }
    for k in ("scores_note", "scores"):  # hand-maintained in bracket_state.json (see runbook)
        if k in prev:
            state[k] = prev[k]
    (DATA / "bracket_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    filled = sum(1 for v in r32_teams.values() if v["s1"] and v["s2"])
    print(f"bracket_state.json written — {'PROVISIONAL' if not complete else 'FINAL'}")
    print(f"  qualifying 3rd-place groups: {', '.join(qualifying)}  (allocation {'OK' if alloc else 'NOT FOUND'})")
    print(f"  R32 matches fully populated: {filled}/16")
    print(f"  knockout results recorded: {len(ko_results)}" + (f"  [{len(ko_warnings)} warning(s)]" if ko_warnings else ""))
    for w in ko_warnings:
        print(f"    warning: {w}")
    if args.verbose:
        for mid in sorted(r32_teams, key=int):
            v = r32_teams[mid]
            print(f"   M{mid}: {v['s1']}  vs  {v['s2']}")


if __name__ == "__main__":
    main()
