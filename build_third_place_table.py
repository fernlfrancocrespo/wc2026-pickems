#!/usr/bin/env python
"""
build_third_place_table.py — scrape FIFA's official 2026 third-place allocation
table (495 combinations) into data/third_place_allocation.json.

This is the authoritative mapping: given which 8 groups' third-placed teams
qualify, it says which group's third-placed team goes to which R32 match. Run
once (the table is fixed); the bracket populate step then just looks it up.

Output: { "<8 sorted group letters>": { "<match#>": "<group letter>", ... }, ... }
e.g. "EFGHIJKL": { "74": "F", "77": "G", "79": "E", "80": "K", "81": "I", ... }
"""
import json
import re
import sys
import requests
from bs4 import BeautifulSoup
from scrape import HEADERS, DATA_DIR

URL = "https://en.wikipedia.org/wiki/2026_FIFA_World_Cup_knockout_stage"
# Allocation columns are labelled by WINNER group (1A,1B,1D,1E,1G,1I,1K,1L); each
# maps to the R32 match whose winner-slot is that group winner.
COL_WINNER_TO_MATCH = {"A": 79, "B": 85, "D": 81, "E": 74, "G": 82, "I": 77, "K": 87, "L": 80}
COL_ORDER = ["A", "B", "D", "E", "G", "I", "K", "L"]  # header order: 1A,1B,1D,1E,1G,1I,1K,1L


def main():
    soup = BeautifulSoup(requests.get(URL, headers=HEADERS, timeout=30).text, "html.parser")
    table = None
    for t in soup.select("table"):
        rows = t.select("tr")
        if len(rows) > 400 and "1A" in rows[0].get_text():
            table = t
            break
    if table is None:
        sys.exit("could not find the 495-row allocation table")

    out, warnings = {}, []
    for row in table.select("tr")[1:]:
        cells = [c.get_text(strip=True) for c in row.select("th,td")]
        groups = sorted(c for c in cells if len(c) == 1 and c in "ABCDEFGHIJKL")
        allocs = [c for c in cells if re.match(r"^3[A-L]$", c)]
        if len(groups) != 8 or len(allocs) != 8:
            warnings.append((cells[:1], len(groups), len(allocs)))
            continue
        assigned = {str(COL_WINNER_TO_MATCH[COL_ORDER[i]]): allocs[i][1] for i in range(8)}
        # sanity: the 8 assigned third-place groups must equal the qualifying set
        if sorted(assigned.values()) != groups:
            warnings.append(("mismatch", "".join(groups), assigned))
            continue
        out["".join(groups)] = assigned

    path = DATA_DIR / "third_place_allocation.json"
    path.write_text(json.dumps(out, separators=(",", ":"), sort_keys=True), encoding="utf-8")
    print(f"wrote {path} with {len(out)} combinations (expected 495)")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings[:10]:
            print("  ", w)


if __name__ == "__main__":
    main()
