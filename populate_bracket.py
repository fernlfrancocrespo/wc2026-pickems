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
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"


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

    state = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "provisional": not complete,
        "group_stage_complete": complete,
        "qualifying_third_groups": qualifying,
        "allocation_found": alloc is not None,
        "r32_teams": r32_teams,
        "results": {},  # match# -> winning team, filled during the knockouts
    }
    (DATA / "bracket_state.json").write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    filled = sum(1 for v in r32_teams.values() if v["s1"] and v["s2"])
    print(f"bracket_state.json written — {'PROVISIONAL' if not complete else 'FINAL'}")
    print(f"  qualifying 3rd-place groups: {', '.join(qualifying)}  (allocation {'OK' if alloc else 'NOT FOUND'})")
    print(f"  R32 matches fully populated: {filled}/16")
    if args.verbose:
        for mid in sorted(r32_teams, key=int):
            v = r32_teams[mid]
            print(f"   M{mid}: {v['s1']}  vs  {v['s2']}")


if __name__ == "__main__":
    main()
