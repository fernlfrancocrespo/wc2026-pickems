"""
World Cup 2026 Pick-'Ems - data scraper
=======================================

Pulls the three datasets the front end needs and writes them to ./data/*.json:

    data/groups.json   - { "A": ["Mexico", "South Africa", ...], ... }   (12 groups A-L)
    data/teams.json    - { "Mexico": { code, iso2, flag_url, confederation, is_host,
                                       group, fifa_rank, recent_form, gf, ga }, ... }
    data/rosters.json  - { "Mexico": [{ name, number, position, club,
                                        dob, age, caps, goals_intl, is_young }, ...] }

Primary source is English Wikipedia via the MediaWiki action API (stable, parseable,
CC-licensed). recent_form / gf / ga are scaffolded null; enrich via a football-data API.

IMPORTANT: page layouts on Wikipedia change. The CSS/heading selectors below are a
strong starting point but you (the Claude Code agent) should RUN this, inspect the
verbose output, and fix selectors against the live HTML. Each step is wrapped so one
failure does not kill the others.

Usage (Windows, from the project folder):
    python -m venv venv
    venv\\Scripts\\activate
    pip install -r requirements.txt
    python scrape.py --verbose
    python scrape.py --only groups        # run a single step while debugging
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import date, datetime, time as _dt_time
from io import StringIO
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    import pandas as pd
except ImportError:
    pd = None

# ----------------------------------------------------------------------------- config

DATA_DIR = Path(__file__).parent / "data"
WIKI_API = "https://en.wikipedia.org/w/api.php"

HEADERS = {
    "User-Agent": "WorldCupPickems/1.0 (personal project; contact: you@example.com)"
}

SQUADS_PAGE   = "2026 FIFA World Cup squads"
TOURNAMENT_PAGE = "2026 FIFA World Cup"
RANKINGS_PAGE = "FIFA Men's World Ranking"

TOURNAMENT_START = date(2026, 6, 11)

HOST_TEAMS = {"United States", "Mexico", "Canada"}

# Squad-page headings that are NOT national teams (stats tables, etc.).
NON_TEAM_HEADINGS = {
    "player representation by league system",
    "player representation by club",
    "player representation by confederation",
    "coaches",
    "statistics",
    "see also",
    "references",
    "notes",
}


def age_at(dob_date: date, ref: date = TOURNAMENT_START) -> int:
    """Exact age in whole years on the reference date."""
    return ref.year - dob_date.year - ((ref.month, ref.day) < (dob_date.month, dob_date.day))


def is_under_23(dob_date: date, ref: date = TOURNAMENT_START) -> bool:
    """
    True if the player has NOT yet turned 23 on the reference date — i.e. they are
    under 23 at the opening match (June 11, 2026). This is the 'young player' pool.
    """
    try:
        twenty_third_birthday = dob_date.replace(year=dob_date.year + 23)
    except ValueError:  # Feb 29 born — use Feb 28
        twenty_third_birthday = dob_date.replace(year=dob_date.year + 23, day=28)
    return twenty_third_birthday > ref

# ----------------------------------------------------------------------------- team name canonicalisation

TEAM_ALIASES = {
    "USA":              "United States",
    "US":               "United States",
    "Korea Republic":   "South Korea",
    "Republic of Korea":"South Korea",
    "IR Iran":          "Iran",
    "Côte d'Ivoire":    "Ivory Coast",
    "Cote d'Ivoire":    "Ivory Coast",
    "Turkiye":          "Türkiye",
    "Turkey":           "Türkiye",
    "Czech Republic":   "Czechia",
    "Congo DR":         "DR Congo",
    "Democratic Republic of the Congo": "DR Congo",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
}

# ----------------------------------------------------------------------------- confederation membership

CONFEDERATIONS: dict[str, set[str]] = {
    "UEFA": {
        "England", "France", "Spain", "Germany", "Italy", "Portugal", "Netherlands",
        "Belgium", "Croatia", "Switzerland", "Denmark", "Poland", "Serbia", "Austria",
        "Ukraine", "Wales", "Scotland", "Czechia", "Türkiye", "Sweden", "Norway",
        "Hungary", "Romania", "Greece", "Slovakia", "Slovenia", "Republic of Ireland",
        "Iceland", "Finland", "Albania", "Georgia", "North Macedonia",
        "Bosnia and Herzegovina", "Montenegro", "Kosovo",
    },
    "CONMEBOL": {
        "Brazil", "Argentina", "Uruguay", "Colombia", "Chile", "Peru", "Ecuador",
        "Paraguay", "Bolivia", "Venezuela",
    },
    "CONCACAF": {
        "United States", "Mexico", "Canada", "Costa Rica", "Panama", "Honduras",
        "Jamaica", "El Salvador", "Curaçao", "Haiti", "Trinidad and Tobago", "Guatemala",
    },
    "CAF": {
        "Morocco", "Senegal", "Nigeria", "Cameroon", "Ghana", "Egypt", "Algeria",
        "Tunisia", "Ivory Coast", "Mali", "South Africa", "Cape Verde",
        "DR Congo", "Burkina Faso", "Guinea", "Angola",
    },
    "AFC": {
        "Japan", "South Korea", "Australia", "Iran", "Saudi Arabia", "Qatar", "Iraq",
        "United Arab Emirates", "Uzbekistan", "Jordan", "China", "Bahrain", "Oman",
    },
    "OFC": {"New Zealand", "New Caledonia", "Tahiti", "Fiji", "Solomon Islands"},
}

# ----------------------------------------------------------------------------- FIFA 3-letter codes

FIFA_CODES: dict[str, str] = {
    # CONCACAF
    "United States": "USA", "Mexico": "MEX", "Canada": "CAN",
    "Costa Rica": "CRC", "Panama": "PAN", "Honduras": "HON",
    "Jamaica": "JAM", "El Salvador": "SLV", "Curaçao": "CUW", "Haiti": "HAI",
    # CONMEBOL
    "Brazil": "BRA", "Argentina": "ARG", "Uruguay": "URU", "Colombia": "COL",
    "Ecuador": "ECU", "Paraguay": "PAR", "Chile": "CHI", "Peru": "PER",
    "Bolivia": "BOL", "Venezuela": "VEN",
    # UEFA
    "England": "ENG", "France": "FRA", "Spain": "ESP", "Germany": "GER",
    "Portugal": "POR", "Netherlands": "NED", "Belgium": "BEL", "Croatia": "CRO",
    "Switzerland": "SUI", "Denmark": "DEN", "Poland": "POL", "Serbia": "SRB",
    "Austria": "AUT", "Ukraine": "UKR", "Sweden": "SWE", "Norway": "NOR",
    "Türkiye": "TUR", "Czechia": "CZE", "Hungary": "HUN", "Romania": "ROU",
    "Slovakia": "SVK", "Slovenia": "SVN", "Scotland": "SCO", "Wales": "WAL",
    "Georgia": "GEO", "Albania": "ALB", "Kosovo": "KVX",
    "Bosnia and Herzegovina": "BIH", "Montenegro": "MNE",
    "North Macedonia": "MKD", "Iceland": "ISL", "Finland": "FIN",
    "Greece": "GRE", "Republic of Ireland": "IRL", "Italy": "ITA",
    # CAF
    "Morocco": "MAR", "Senegal": "SEN", "Nigeria": "NGA", "Cameroon": "CMR",
    "Ghana": "GHA", "Egypt": "EGY", "Algeria": "ALG", "Tunisia": "TUN",
    "Ivory Coast": "CIV", "Mali": "MLI", "South Africa": "RSA",
    "Cape Verde": "CPV", "DR Congo": "COD", "Burkina Faso": "BFA",
    "Guinea": "GUI", "Angola": "ANG",
    # AFC
    "Japan": "JPN", "South Korea": "KOR", "Australia": "AUS", "Iran": "IRN",
    "Saudi Arabia": "KSA", "Qatar": "QAT", "Iraq": "IRQ",
    "United Arab Emirates": "UAE", "Uzbekistan": "UZB", "Jordan": "JOR",
    "China": "CHN", "Bahrain": "BHR", "Oman": "OMA",
    # OFC
    "New Zealand": "NZL", "New Caledonia": "NCL", "Tahiti": "TAH",
    "Fiji": "FIJ", "Solomon Islands": "SOL",
}

# ----------------------------------------------------------------------------- ISO 3166-1 alpha-2 (for flagcdn.com)
# flag URL: https://flagcdn.com/w40/{iso2}.png
# Special values: gb-eng, gb-sct, gb-wls for the British home nations.

ISO2_CODES: dict[str, str] = {
    # CONCACAF
    "United States": "us", "Mexico": "mx", "Canada": "ca",
    "Costa Rica": "cr", "Panama": "pa", "Honduras": "hn",
    "Jamaica": "jm", "El Salvador": "sv", "Curaçao": "cw", "Haiti": "ht",
    # CONMEBOL
    "Brazil": "br", "Argentina": "ar", "Uruguay": "uy", "Colombia": "co",
    "Ecuador": "ec", "Paraguay": "py", "Chile": "cl", "Peru": "pe",
    "Bolivia": "bo", "Venezuela": "ve",
    # UEFA
    "England": "gb-eng", "France": "fr", "Spain": "es", "Germany": "de",
    "Portugal": "pt", "Netherlands": "nl", "Belgium": "be", "Croatia": "hr",
    "Switzerland": "ch", "Denmark": "dk", "Poland": "pl", "Serbia": "rs",
    "Austria": "at", "Ukraine": "ua", "Sweden": "se", "Norway": "no",
    "Türkiye": "tr", "Czechia": "cz", "Hungary": "hu", "Romania": "ro",
    "Slovakia": "sk", "Slovenia": "si", "Scotland": "gb-sct", "Wales": "gb-wls",
    "Georgia": "ge", "Albania": "al", "Kosovo": "xk",
    "Bosnia and Herzegovina": "ba", "Montenegro": "me",
    "North Macedonia": "mk", "Iceland": "is", "Finland": "fi",
    "Greece": "gr", "Republic of Ireland": "ie", "Italy": "it",
    # CAF
    "Morocco": "ma", "Senegal": "sn", "Nigeria": "ng", "Cameroon": "cm",
    "Ghana": "gh", "Egypt": "eg", "Algeria": "dz", "Tunisia": "tn",
    "Ivory Coast": "ci", "Mali": "ml", "South Africa": "za",
    "Cape Verde": "cv", "DR Congo": "cd", "Burkina Faso": "bf",
    "Guinea": "gn", "Angola": "ao",
    # AFC
    "Japan": "jp", "South Korea": "kr", "Australia": "au", "Iran": "ir",
    "Saudi Arabia": "sa", "Qatar": "qa", "Iraq": "iq",
    "United Arab Emirates": "ae", "Uzbekistan": "uz", "Jordan": "jo",
    "China": "cn", "Bahrain": "bh", "Oman": "om",
    # OFC
    "New Zealand": "nz", "New Caledonia": "nc", "Tahiti": "pf",
    "Fiji": "fj", "Solomon Islands": "sb",
}

FLAG_BASE = "https://flagcdn.com/w40/{iso2}.png"

# ----------------------------------------------------------------------------- form: name → international-football.net slug
# Only entries that differ from the canonical name are listed here.
# URL pattern: https://www.international-football.net/country?team=<name>
FORM_URL_NAMES: dict[str, str] = {
    "DR Congo":            "Dem. Rep. of Congo",
    "Türkiye":             "Turkey",
    "Republic of Ireland": "Ireland",
    "Czechia":             "Czech Republic",
}

# ----------------------------------------------------------------------------- helpers

def confederation_for(team: str) -> str:
    for conf, members in CONFEDERATIONS.items():
        if team in members:
            return conf
    return "UNKNOWN"


def normalize(name: str) -> str:
    name = name.strip()
    return TEAM_ALIASES.get(name, name)


def log(msg: str, verbose: bool = True) -> None:
    if verbose:
        print(msg, file=sys.stderr)


def fetch_html(page: str, verbose: bool = False) -> BeautifulSoup:
    params = {
        "action": "parse",
        "page": page,
        "format": "json",
        "prop": "text",
        "formatversion": "2",
        "redirects": "1",
    }
    log(f"  fetching: {page}", verbose)
    for attempt in range(5):
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            log(f"  429 rate-limited; waiting {retry_after}s (attempt {attempt + 1}/5)", True)
            time.sleep(retry_after)
            continue
        resp.raise_for_status()
        break
    else:
        resp.raise_for_status()
    payload = resp.json()
    if "error" in payload:
        raise RuntimeError(f"Wikipedia API error for '{page}': {payload['error']}")
    html = payload["parse"]["text"]
    time.sleep(2)
    return BeautifulSoup(html, "lxml")


def heading_text(tag) -> str:
    span = tag.find(class_="mw-headline")
    return (span.get_text() if span else tag.get_text()).strip()


def parse_dob(cells) -> str | None:
    """Extract ISO date string from a Wikipedia bday span, or None."""
    for cell in cells:
        bday = cell.find("span", class_="bday")
        if bday:
            text = bday.get_text().strip()
            if re.match(r"\d{4}-\d{2}-\d{2}", text):
                return text
    return None


def parse_int_cell(text: str) -> int | None:
    """Parse a cell that should be a plain integer (caps, goals, shirt number)."""
    clean = text.split("[")[0].strip()
    try:
        return int(clean)
    except ValueError:
        return None


# ----------------------------------------------------------------------------- scrape steps

def scrape_groups(verbose: bool = False) -> tuple[dict[str, list[str]], dict[str, str]]:
    """
    Returns (groups, team_to_group).
      groups       = { "A": ["Mexico", ...], ... }   (12 groups, 4 teams each)
      team_to_group = { "Mexico": "A", ... }
    """
    soup = fetch_html(TOURNAMENT_PAGE, verbose)
    groups: dict[str, list[str]] = {}

    for heading in soup.find_all(["h3", "h4"]):
        text = heading_text(heading)
        if not text.lower().startswith("group "):
            continue
        letter = text.split()[1].strip().upper()
        if letter not in list("ABCDEFGHIJKL"):
            continue
        table = heading.find_next("table", class_="wikitable")
        if table is None:
            log(f"  [groups] no table after '{text}'", verbose)
            continue
        teams: list[str] = []
        for row in table.select("tr"):
            link = row.find("a", title=True)
            if not link:
                continue
            raw = link.get_text().strip()
            if raw.lower() in {"v", "vs"}:
                continue
            team = normalize(raw)
            if team and team not in teams:
                teams.append(team)
        teams = teams[:4]
        if len(teams) == 4:
            groups[letter] = teams
            log(f"  [groups] {letter}: {teams}", verbose)
        else:
            log(f"  [groups] {letter}: parsed {len(teams)}/4 -> CHECK", verbose)

    if len(groups) != 12:
        log(f"  [groups] WARNING: parsed {len(groups)}/12 groups", True)

    groups = dict(sorted(groups.items()))
    team_to_group = {team: letter for letter, members in groups.items() for team in members}
    return groups, team_to_group


def scrape_rosters(valid_teams: set[str] | None = None, verbose: bool = False) -> dict[str, list[dict]]:
    """
    All 48 squads from the squads page.
    Each player record: { name, number, position, club, dob, age, caps, goals_intl, is_young }

    valid_teams: if provided (the 48 WC teams), only those headings are kept — this
    drops non-team tables like 'Player representation by league system'.
    """
    soup = fetch_html(SQUADS_PAGE, verbose)
    rosters: dict[str, list[dict]] = {}
    _POSITIONS = {"GK", "DF", "MF", "FW"}

    for heading in soup.find_all("h3"):
        country = normalize(heading_text(heading))

        # Skip known non-team headings and, if we know the WC team list, anything not on it.
        if country.lower() in NON_TEAM_HEADINGS:
            continue
        if valid_teams is not None and country not in valid_teams:
            log(f"  [rosters] skipping non-team heading: '{country}'", verbose)
            continue

        table = heading.find_next("table", class_="wikitable")
        if table is None:
            continue

        # Read column headers to locate the caps/goals columns by index.
        header_row = table.find("tr")
        col_names: list[str] = []
        if header_row:
            col_names = [th.get_text(" ", strip=True).lower()
                         for th in header_row.find_all(["th", "td"])]

        caps_idx  = next((i for i, h in enumerate(col_names) if "cap" in h), None)
        goals_idx = next((i for i, h in enumerate(col_names)
                          if "goal" in h and "gk" not in h and i != caps_idx), None)

        players: list[dict] = []
        for row in table.select("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            texts = [c.get_text(" ", strip=True) for c in cells]

            # --- number ---
            number = parse_int_cell(texts[0]) if texts else None

            # --- position: look for exact GK/DF/MF/FW, ignoring footnotes ---
            position = None
            for t in texts:
                candidate = t.split("[")[0].strip()
                if candidate in _POSITIONS:
                    position = candidate
                    break

            # --- player name: first linked text that isn't a position code or digit ---
            name_link = None
            for cell in cells:
                a = cell.find("a", title=True)
                if a:
                    t = a.get_text().strip()
                    if t and t.split("[")[0].strip() not in _POSITIONS and not t.isdigit():
                        name_link = a
                        break
            if not name_link:
                continue
            name = name_link.get_text().strip()

            # --- DOB via hidden bday span ---
            dob_str = parse_dob(cells)
            dob_date: date | None = None
            if dob_str:
                try:
                    dob_date = date.fromisoformat(dob_str)
                except ValueError:
                    pass

            age = age_at(dob_date) if dob_date else None
            is_young = is_under_23(dob_date) if dob_date else None

            # --- caps and goals by column index if detected, else None ---
            caps       = parse_int_cell(texts[caps_idx])  if caps_idx  is not None and caps_idx  < len(texts) else None
            goals_intl = parse_int_cell(texts[goals_idx]) if goals_idx is not None and goals_idx < len(texts) else None

            # --- club: last cell, strip footnotes ---
            club = texts[-1].split("[")[0].strip() if texts else None

            players.append({
                "name":        name,
                "number":      number,
                "position":    position,
                "club":        club,
                "dob":         dob_str,
                "age":         age,
                "caps":        caps,
                "goals_intl":  goals_intl,
                "is_young":    is_young,
            })

        if 18 <= len(players) <= 35:
            rosters[country] = players
            log(f"  [rosters] {country}: {len(players)} players", verbose)

    if len(rosters) != 48:
        log(f"  [rosters] WARNING: parsed {len(rosters)}/48 squads", True)
    return dict(sorted(rosters.items()))


def parse_rankings_html(content: str, verbose: bool = False) -> dict[str, int]:
    """
    Parse FIFA men's rankings from a saved copy of
    https://inside.fifa.com/fifa-world-ranking/men

    The page is client-side rendered; save the fully-loaded page via
    'Save Page Now' or the browser's 'Save as Complete Page', then pass
    that file with --rankings-html PATH.

    Key HTML patterns (class names contain hash suffixes that may change):
        <h3 class="custom-rank-cell_rankNumber__...">1</h3>
        <a class="custom-team-cell_teamName__...">France</a>
    Ranks and team-name links appear in the same order in the DOM.
    """
    rank_nums = re.findall(r'custom-rank-cell_rankNumber[^"]*">(\d+)</h3>', content)
    team_names = re.findall(r'custom-team-cell_teamName[^"]*[^>]*>([^<]+)</a>', content)

    if not rank_nums or not team_names:
        log("  [rankings] No ranking data found — check that the file is a fully-rendered page", True)
        return {}

    if len(rank_nums) != len(team_names):
        log(f"  [rankings] Count mismatch: {len(rank_nums)} ranks vs {len(team_names)} names "
            f"— using min({len(rank_nums)}, {len(team_names)})", True)

    ranks: dict[str, int] = {}
    for rank_str, raw_name in zip(rank_nums, team_names):
        team = normalize(raw_name.strip())
        try:
            ranks.setdefault(team, int(rank_str))
        except ValueError:
            pass

    log(f"  [rankings] parsed {len(ranks)} teams from local HTML", verbose)
    return ranks


def scrape_rankings(html_file: str | None = None, verbose: bool = False) -> dict[str, int]:
    """
    Load FIFA men's rankings.

    Preferred: pass --rankings-html pointing to a saved copy of the FIFA
    rankings page (inside.fifa.com/fifa-world-ranking/men). The page
    requires JS to render so we can't fetch it with requests.

    Fallback: Wikipedia rankings table (less accurate, may be stale).
    """
    if html_file:
        try:
            with open(html_file, encoding="utf-8", errors="ignore") as f:
                content = f.read()
            return parse_rankings_html(content, verbose)
        except OSError as e:
            log(f"  [rankings] Could not open {html_file}: {e}", True)
            return {}

    # --- Wikipedia fallback ---
    log("  [rankings] No HTML file provided; falling back to Wikipedia (may be stale)", True)
    soup = fetch_html(RANKINGS_PAGE, verbose)
    ranks: dict[str, int] = {}

    if pd is None:
        log("  [rankings] pandas not installed; pip install pandas", True)
        return ranks

    for table in soup.find_all("table", class_="wikitable"):
        try:
            df = pd.read_html(StringIO(str(table)))[0]
        except ValueError:
            continue
        cols = [str(c).lower() for c in df.columns]
        rank_col = next((c for c, lc in zip(df.columns, cols) if "rank" in lc or "pos" in lc or "rk" in lc), None)
        team_col = next((c for c, lc in zip(df.columns, cols) if "team" in lc or "nation" in lc), None)
        if rank_col is None or team_col is None:
            continue
        for _, r in df.iterrows():
            try:
                team = normalize(str(r[team_col]))
                rank = int(str(r[rank_col]).split()[0])
            except (ValueError, KeyError):
                continue
            ranks.setdefault(team, rank)
        if ranks:
            break

    log(f"  [rankings] parsed {len(ranks)} ranked teams from Wikipedia", verbose)
    return ranks


# ----------------------------------------------------------------------------- form scraping

def parse_form_html(content: str, team_name: str, verbose: bool = False) -> list[dict]:
    """
    Parse the 'last international games' table from an
    https://www.international-football.net/country?team=<name> page.

    Returns up to 10 match dicts:
        { result, date, location, competition, opponent, score, match_url }
    """
    soup = BeautifulSoup(content, "lxml")

    # Find the section heading
    section = None
    for h in soup.find_all(["h2", "h3"]):
        if "last international games" in h.get_text().lower():
            section = h
            break
    if section is None:
        log(f"  [form] '{team_name}': 'last international games' section not found", verbose)
        return []

    table = section.find_next("table")
    if table is None:
        log(f"  [form] '{team_name}': no table after section heading", verbose)
        return []

    matches: list[dict] = []
    ctx: dict = {"date": "", "location": "", "competition": ""}

    for tr in table.find_all("tr"):
        classes = tr.get("class", [])

        # ── Context row (mobile): "March 31st, 2026 in Saudi Arabia · AFC qualifier" ──
        if "smartphone" in classes:
            raw = re.sub(r"\s+", " ", tr.get_text(" ", strip=True)).strip()
            # Single-pass regex: capture date, location, and (optionally) competition.
            # The separator between location and competition can be ·, –, �, or
            # even a plain hyphen, depending on encoding and browser rendering.
            full = re.match(
                r"(.+?\d{4})\s+in\s+(.+?)\s*[··�–—\-]{1,3}\s*(.+)",
                raw,
            )
            if full:
                ctx = {
                    "date":        full.group(1).strip(),
                    "location":    full.group(2).strip(),
                    "competition": full.group(3).strip(),
                }
            else:
                # No separator found — try date + location only
                partial = re.match(r"(.+?\d{4})\s+in\s+(.+)", raw)
                ctx = {
                    "date":        partial.group(1).strip() if partial else raw,
                    "location":    partial.group(2).strip() if partial else "",
                    "competition": "",
                }
            continue

        # ── Match data row ──
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        # Result: W / D / L from the strong tag in the first cell
        result_tag = cells[0].find("strong")
        if result_tag is None or result_tag.get_text(strip=True) not in ("W", "D", "L"):
            continue
        result = result_tag.get_text(strip=True)

        # Opponent: the team cell that links to a different team page
        opponent = ""
        for cell in cells:
            onclick = cell.get("onclick", "")
            m2 = re.search(r"team=([^'\"&#]+)", onclick)
            if m2:
                cand = normalize(requests.utils.unquote(m2.group(1)).strip())
                if cand.lower() != team_name.lower():
                    opponent = cand
                    break

        # Score + match URL: cell with match-details link
        score = ""
        match_url = ""
        for cell in cells:
            onclick = cell.get("onclick", "")
            if "match-details" in onclick:
                span = cell.find("span", class_="opensans")
                if span:
                    score = span.get_text(strip=True).replace("\xa0", "").replace(" ", "")
                url_m = re.search(r"'(https://www\.international-football\.net/match-details\?id=\d+)", onclick)
                if url_m:
                    match_url = url_m.group(1)
                break

        if result:
            matches.append({
                "result":      result,
                "date":        ctx["date"],
                "location":    ctx["location"],
                "competition": ctx["competition"],
                "opponent":    opponent,
                "score":       score,
                "match_url":   match_url,
            })

        if len(matches) >= 10:
            break

    log(f"  [form] {team_name}: {len(matches)} matches", verbose)
    return matches


def scrape_form(team_names: list[str], verbose: bool = False) -> dict[str, list[dict]]:
    """
    Fetch last-10-games form for each team from international-football.net.
    Writes data/form.json.  Takes ~1 min for 48 teams (1.5 s delay between requests).
    """
    BASE = "https://www.international-football.net/country?team="
    form: dict[str, list[dict]] = {}

    for i, team in enumerate(team_names, 1):
        url_name = FORM_URL_NAMES.get(team, team)
        url = BASE + requests.utils.quote(url_name)
        log(f"  [form] ({i}/{len(team_names)}) {team}…", verbose)

        for attempt in range(4):
            try:
                resp = requests.get(url, headers=HEADERS, timeout=25)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5 * (attempt + 1)))
                    log(f"  [form] rate-limited, waiting {wait}s", True)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                matches = parse_form_html(resp.text, team, verbose)
                if matches:
                    form[team] = matches
                time.sleep(1.5)
                break
            except Exception as e:
                log(f"  [form] {team} attempt {attempt+1} failed: {e}", True)
                time.sleep(3)

    found = len(form)
    missed = [t for t in team_names if t not in form]
    if missed:
        log(f"  [form] WARNING: no data for {missed}", True)
    log(f"  [form] complete: {found}/{len(team_names)} teams", True)
    return dict(sorted(form.items()))


# ----------------------------------------------------------------------------- schedule (group-stage fixtures)

def parse_schedule_txt(content: str, team_to_group: dict[str, str], verbose: bool = False) -> dict[str, list[dict]]:
    """
    Parse a plain-text dump of the 2026 match schedule into per-group fixtures.

    Expected line shape (tabs/blank lines ignored), repeated per match:
        <Home team>
          v
        <Away team>
        <time, e.g. 3:00 PM>
        <venue, e.g. Estadio Banorte, Mexico City, Mexico>
    with a date header line ("Thursday, June 11, 2026") before each day's block.

    Only GROUP-STAGE matches are kept (knockout rows reference placeholders like
    "Group A 2nd Place", which aren't in team_to_group and are skipped).

    Returns: { "A": [ {matchday, home, away, date, venue}, ... ], ... }
    """
    DATE_RE = re.compile(r"^[A-Za-z]+day,\s+[A-Za-z]+\s+\d{1,2},\s+\d{4}$")
    TIME_RE = re.compile(r"^\d{1,2}:\d{2}\s*(AM|PM)$", re.I)
    SKIP = {"MATCH", "TIME", "TV", "LOCATION", "TICKETS"}

    tokens: list[str] = []
    for raw in content.splitlines():
        s = raw.strip().strip('"').strip()
        if not s:
            continue
        up = s.upper()
        if up in SKIP or up.startswith("BETTING"):
            continue
        tokens.append(s)

    raw_matches: list[dict] = []
    current_date: date | None = None
    for i, tok in enumerate(tokens):
        if DATE_RE.match(tok):
            try:
                current_date = datetime.strptime(tok, "%A, %B %d, %Y").date()
            except ValueError:
                current_date = None
            continue
        if tok.lower() == "v":
            if i == 0 or i + 1 >= len(tokens):
                continue
            home = normalize(tokens[i - 1])
            away = normalize(tokens[i + 1])
            time_str, venue = "", ""
            if i + 2 < len(tokens) and TIME_RE.match(tokens[i + 2]):
                time_str = tokens[i + 2].upper().replace(" ", " ")
                if i + 3 < len(tokens):
                    venue = tokens[i + 3]
            elif i + 2 < len(tokens):
                venue = tokens[i + 2]
            raw_matches.append({"home": home, "away": away, "time": time_str,
                                "venue": venue, "date": current_date})

    # Group by group letter (group stage only)
    by_group: dict[str, list[dict]] = {}
    for m in raw_matches:
        g = team_to_group.get(m["home"]) or team_to_group.get(m["away"])
        if not g:
            continue
        by_group.setdefault(g, []).append(m)

    def sort_key(m: dict):
        d = m["date"] or date.max
        try:
            tt = datetime.strptime(m["time"], "%I:%M %p").time() if m["time"] else _dt_time.min
        except ValueError:
            tt = _dt_time.min
        return (d, tt)

    schedule: dict[str, list[dict]] = {}
    for g, ms in by_group.items():
        ms.sort(key=sort_key)
        out = []
        for idx, m in enumerate(ms):
            d = m["date"]
            date_disp = d.strftime("%b %d") if d else ""
            if m["time"]:
                date_disp = f"{date_disp} · {m['time']}".strip(" ·")
            out.append({
                "matchday": idx // 2 + 1,   # 2 matches per matchday after sort
                "home":     m["home"],
                "away":     m["away"],
                "date":     date_disp,
                "venue":    m["venue"],
            })
        schedule[g] = out
        log(f"  [schedule] Group {g}: {len(out)} matches", verbose)

    total = sum(len(v) for v in schedule.values())
    if total != 72:
        log(f"  [schedule] WARNING: parsed {total}/72 group-stage matches", True)
    return dict(sorted(schedule.items()))


def scrape_schedule(txt_file: str, team_to_group: dict[str, str], verbose: bool = False) -> dict[str, list[dict]]:
    with open(txt_file, encoding="utf-8", errors="ignore") as f:
        return parse_schedule_txt(f.read(), team_to_group, verbose)


# ----------------------------------------------------------------------------- live standings

def build_live_standings(
    groups: dict[str, list[str]],
    team_to_group: dict[str, str],
    results_text: str = "",
    verbose: bool = False,
) -> dict:
    """
    Compute live group-stage standings from match-result lines and write live.json.

    results_text lines look like:  "Mexico 2-1 South Africa"  (one per played match;
    '#' lines and blanks ignored). With no results, every team starts 0-0-0 so the
    standings page can render the groups immediately at launch.

    Output: { updated, matches_played, groups: { "A": [ {team, iso2, code,
              pld, w, d, l, gf, ga, gd, pts}, ... sorted ], ... } }
    """
    standings = {
        team: {"team": team, "iso2": ISO2_CODES.get(team), "code": FIFA_CODES.get(team),
               "pld": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "gd": 0, "pts": 0}
        for team in team_to_group
    }

    line_re = re.compile(r"^(.+?)\s+(\d+)\s*[-x:]\s*(\d+)\s+(.+?)\s*$")
    played = 0
    for raw in (results_text or "").splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        m = line_re.match(s)
        if not m:
            log(f"  [results] could not parse: {s!r}", verbose)
            continue
        home, hs, ascore, away = normalize(m.group(1)), int(m.group(2)), int(m.group(3)), normalize(m.group(4))
        if home not in standings or away not in standings:
            log(f"  [results] unknown team in: {s!r}", verbose)
            continue
        if team_to_group.get(home) != team_to_group.get(away):
            # cross-group = knockout; doesn't affect group standings
            continue
        for team, gf, ga in ((home, hs, ascore), (away, ascore, hs)):
            st = standings[team]
            st["pld"] += 1; st["gf"] += gf; st["ga"] += ga; st["gd"] = st["gf"] - st["ga"]
            if gf > ga:   st["w"] += 1; st["pts"] += 3
            elif gf == ga: st["d"] += 1; st["pts"] += 1
            else:          st["l"] += 1
        played += 1

    out: dict[str, list[dict]] = {}
    for letter, teams in groups.items():
        rows = [standings[t] for t in teams if t in standings]
        rows.sort(key=lambda r: (-r["pts"], -r["gd"], -r["gf"], r["team"]))
        out[letter] = rows

    log(f"  [results] {played} matches → standings for {len(out)} groups", True)
    return {
        "updated": datetime.now().isoformat(timespec="seconds"),
        "matches_played": played,
        "groups": dict(sorted(out.items())),
    }


# ----------------------------------------------------------------------------- player photos

def _wiki_query(params: dict, verbose: bool = False) -> dict:
    """GET the MediaWiki query API with light 429 retry."""
    for attempt in range(5):
        resp = requests.get(WIKI_API, params=params, headers=HEADERS, timeout=30)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", 2 ** (attempt + 1)))
            log(f"  [photos] 429 — waiting {wait}s", True)
            time.sleep(wait)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _squad_titles(soup: BeautifulSoup, verbose: bool = False) -> dict[str, dict[str, str]]:
    """
    From the squads page soup, return { team: { player_name: wiki_title } }.
    Player links live in the row header cell: <th scope="row"><a title="...">Name</a>.
    """
    out: dict[str, dict[str, str]] = {}
    for heading in soup.find_all("h3"):
        country = normalize(heading_text(heading))
        if country.lower() in NON_TEAM_HEADINGS:
            continue
        table = heading.find_next("table", class_="wikitable")
        if table is None:
            continue
        players: dict[str, str] = {}
        for row in table.select("tr"):
            th = row.find("th", attrs={"scope": "row"})
            if th is None:
                continue
            a = th.find("a", title=True)
            if not a:
                continue
            name = a.get_text().strip()
            title = a.get("title", "").strip()
            if name and title and "(" not in title.split()[-1]:
                players[name] = title
        if 15 <= len(players) <= 40:
            out[country] = players
    return out


def scrape_photos(squads_html: str | None = None, verbose: bool = False) -> dict[str, list[dict]]:
    """
    Add a `photo` field (Wikipedia profile thumbnail URL, or null) to every player
    in rosters.json. Source of player→article titles is the squads page; thumbnails
    come from the MediaWiki `pageimages` API. Run this AFTER rosters.

    Pass --squads-html PATH to parse a saved copy of the squads page (avoids a re-fetch);
    otherwise the page is fetched via the API.
    """
    rosters_path = DATA_DIR / "rosters.json"
    if not rosters_path.exists():
        log("  [photos] rosters.json missing — run --only rosters first", True)
        return {}
    rosters = json.loads(rosters_path.read_text(encoding="utf-8"))

    if squads_html:
        soup = BeautifulSoup(open(squads_html, encoding="utf-8", errors="ignore").read(), "lxml")
    else:
        soup = fetch_html(SQUADS_PAGE, verbose)

    team_titles = _squad_titles(soup, verbose)
    all_titles = sorted({t for players in team_titles.values() for t in players.values()})
    log(f"  [photos] {len(all_titles)} player titles across {len(team_titles)} teams", True)

    # Batch the pageimages query (50 titles per request).
    title_to_thumb: dict[str, str] = {}
    for i in range(0, len(all_titles), 50):
        batch = all_titles[i:i + 50]
        data = _wiki_query({
            "action": "query", "format": "json", "formatversion": "2",
            "prop": "pageimages", "piprop": "thumbnail", "pithumbsize": "200",
            "titles": "|".join(batch), "redirects": "1",
        }, verbose)
        q = data.get("query", {})
        norm = {n["from"]: n["to"] for n in q.get("normalized", [])}
        redir = {r["from"]: r["to"] for r in q.get("redirects", [])}
        page_thumb = {p["title"]: p.get("thumbnail", {}).get("source")
                      for p in q.get("pages", []) if "title" in p}
        for title in batch:
            t = redir.get(norm.get(title, title), norm.get(title, title))
            thumb = page_thumb.get(t)
            if thumb:
                title_to_thumb[title] = thumb
        log(f"  [photos] batch {i // 50 + 1}/{(len(all_titles) + 49) // 50}: "
            f"{len(title_to_thumb)} photos so far", verbose)
        time.sleep(0.6)

    # Merge into rosters by team + player name.
    matched = 0
    for team, players in rosters.items():
        name_to_title = team_titles.get(team, {})
        for p in players:
            title = name_to_title.get(p["name"])
            photo = title_to_thumb.get(title) if title else None
            p["photo"] = photo
            if photo:
                matched += 1

    total = sum(len(v) for v in rosters.values())
    log(f"  [photos] matched {matched}/{total} players to a photo", True)
    return dict(sorted(rosters.items()))


# ----------------------------------------------------------------------------- assemble

def build_teams(
    groups: dict[str, list[str]],
    team_to_group: dict[str, str],
    ranks: dict[str, int],
    form: dict[str, list[dict]] | None = None,
    verbose: bool = False,
) -> dict[str, dict]:
    teams: dict[str, dict] = {}
    all_teams = sorted({t for members in groups.values() for t in members})
    for team in all_teams:
        conf = confederation_for(team)
        if conf == "UNKNOWN":
            log(f"  [teams] UNKNOWN confederation for '{team}' - add to CONFEDERATIONS", True)

        iso2 = ISO2_CODES.get(team)
        if iso2 is None:
            log(f"  [teams] missing ISO2 code for '{team}' - add to ISO2_CODES", True)

        if team not in FIFA_CODES:
            log(f"  [teams] missing FIFA code for '{team}' - add to FIFA_CODES", True)

        # recent_form: last 5 results from form data, e.g. ["W","D","L","W","W"]
        recent: list[str] | None = None
        if form and team in form:
            recent = [m["result"] for m in form[team][:5]]

        teams[team] = {
            "code":          FIFA_CODES.get(team),
            "iso2":          iso2,
            "flag_url":      FLAG_BASE.format(iso2=iso2) if iso2 else None,
            "confederation": conf,
            "is_host":       team in HOST_TEAMS,
            "group":         team_to_group.get(team),
            "fifa_rank":     ranks.get(team),
            "recent_form":   recent,
            "goals_for":     None,
            "goals_against": None,
        }
    return teams


def write_json(name: str, obj) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / name
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path}  ({len(obj)} entries)")


# ----------------------------------------------------------------------------- main

def main() -> None:
    ap = argparse.ArgumentParser(description="Scrape World Cup 2026 data into ./data")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--only", choices=["groups", "rosters", "rankings", "form", "schedule", "results", "photos"],
                    help="run a single step (for debugging)")
    ap.add_argument("--squads-html", metavar="PATH",
                    help="path to a saved copy of the 2026 squads page (for --only photos)")
    ap.add_argument("--rankings-html", metavar="PATH",
                    help="path to a saved copy of inside.fifa.com/fifa-world-ranking/men "
                         "(fully rendered page, required for accurate ranks)")
    ap.add_argument("--schedule-txt", metavar="PATH",
                    help="path to a plain-text dump of the 2026 match schedule "
                         "(parsed into data/schedule.json)")
    ap.add_argument("--results-txt", metavar="PATH",
                    help="path to a text file of played results ('Mexico 2-1 South Africa' "
                         "per line) → live group standings in data/live.json")
    args = ap.parse_args()
    v = args.verbose

    groups: dict[str, list[str]] = {}
    team_to_group: dict[str, str] = {}
    rosters: dict[str, list[dict]] = {}
    ranks: dict[str, int] = {}
    form: dict[str, list[dict]] = {}

    def wc_team_set() -> set[str]:
        """The 48 WC teams, from this run's groups or a saved groups.json."""
        return set(wc_team_to_group().keys())

    def wc_team_to_group() -> dict[str, str]:
        """{team: group} from this run's groups or a saved groups.json."""
        return {t: letter for letter, members in wc_groups().items() for t in members}

    def wc_groups() -> dict[str, list[str]]:
        """{letter: [teams]} from this run's groups or a saved groups.json."""
        if groups:
            return groups
        gp = DATA_DIR / "groups.json"
        if gp.exists():
            return json.loads(gp.read_text(encoding="utf-8"))
        return {}

    if args.only in (None, "groups"):
        print("== groups ==")
        try:
            groups, team_to_group = scrape_groups(v)
            write_json("groups.json", groups)
        except Exception as e:
            print(f"  groups FAILED: {e}", file=sys.stderr)

    if args.only in (None, "rosters"):
        print("== rosters ==")
        try:
            valid = wc_team_set() or None
            if valid is None:
                print("  rosters NOTE: no groups.json yet — non-team tables can't be filtered. "
                      "Run --only groups first for a clean roster.", file=sys.stderr)
            rosters = scrape_rosters(valid_teams=valid, verbose=v)
            write_json("rosters.json", rosters)
        except Exception as e:
            print(f"  rosters FAILED: {e}", file=sys.stderr)

    if args.only in (None, "rankings"):
        print("== rankings ==")
        try:
            ranks = scrape_rankings(html_file=args.rankings_html, verbose=v)
        except Exception as e:
            print(f"  rankings FAILED: {e}", file=sys.stderr)

    if args.only in (None, "form"):
        print("== form ==")
        try:
            team_list = sorted(wc_team_set())
            if team_list:
                form = scrape_form(team_list, v)
                write_json("form.json", form)
            else:
                print("  form SKIP: run --only groups first to build the team list", file=sys.stderr)
        except Exception as e:
            print(f"  form FAILED: {e}", file=sys.stderr)

    if args.only == "schedule" or (args.only is None and args.schedule_txt):
        print("== schedule ==")
        try:
            if not args.schedule_txt:
                print("  schedule SKIP: pass --schedule-txt PATH", file=sys.stderr)
            else:
                ttg = wc_team_to_group()
                if not ttg:
                    print("  schedule SKIP: run --only groups first", file=sys.stderr)
                else:
                    schedule = scrape_schedule(args.schedule_txt, ttg, v)
                    write_json("schedule.json", schedule)
        except Exception as e:
            print(f"  schedule FAILED: {e}", file=sys.stderr)

    if args.only == "photos":
        print("== photos ==")
        try:
            photo_rosters = scrape_photos(squads_html=args.squads_html, verbose=v)
            if photo_rosters:
                write_json("rosters.json", photo_rosters)
        except Exception as e:
            print(f"  photos FAILED: {e}", file=sys.stderr)

    if args.only == "results" or (args.only is None and args.results_txt):
        print("== results / standings ==")
        try:
            g = wc_groups()
            ttg = wc_team_to_group()
            if not g:
                print("  results SKIP: run --only groups first", file=sys.stderr)
            else:
                results_text = ""
                if args.results_txt:
                    with open(args.results_txt, encoding="utf-8", errors="ignore") as f:
                        results_text = f.read()
                else:
                    print("  results NOTE: no --results-txt; writing zeroed standings.", file=sys.stderr)
                live = build_live_standings(g, ttg, results_text, v)
                write_json("live.json", live)
        except Exception as e:
            print(f"  results FAILED: {e}", file=sys.stderr)

    if args.only is None:
        print("== teams (merged) ==")
        # Load form if it wasn't scraped this run
        if not form:
            form_path = DATA_DIR / "form.json"
            if form_path.exists():
                form = json.loads(form_path.read_text(encoding="utf-8"))
        teams = build_teams(groups, team_to_group, ranks, form, v)
        write_json("teams.json", teams)

    print("\nDone. Re-run a step with --only <step> --verbose to debug selectors.")


if __name__ == "__main__":
    main()
