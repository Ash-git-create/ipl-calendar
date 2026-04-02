#!/usr/bin/env python3
"""
IPL Calendar Generator
Primary source: CricAPI (structured JSON)
Fallback source: Cricbuzz (DOM scraping)
"""

import logging
import os
import re
import sys
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path

import pytz
import requests
from bs4 import BeautifulSoup
from icalendar import Calendar, Event

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

API_KEY = os.environ.get("CRICAPI_KEY")
BASE_URL = "https://api.cricapi.com/v1"
IST = pytz.timezone("Asia/Kolkata")
YEAR = "2026"
ROOT_DIR = Path(__file__).resolve().parent.parent
CALENDARS_DIR = ROOT_DIR / "calendars"

# Note: Series IDs change yearly. The default is based on the provided URL.
# You can override this in GitHub Actions via env variables when a new year drops.
CRICBUZZ_URL = os.environ.get(
    "CRICBUZZ_URL",
    f"https://www.cricbuzz.com/cricket-series/9241/indian-premier-league-{YEAR}/matches",
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Team filtering helpers -----------------------------------------------------

TEAM_ALIASES = {
    "CSK": ["chennai super kings", "csk"],
    "DC": ["delhi capitals", "dc", "delhi daredevils"],
    "GT": ["gujarat titans", "gt"],
    "KKR": ["kolkata knight riders", "kkr"],
    "LSG": ["lucknow super giants", "lsg"],
    "MI": ["mumbai indians", "mi"],
    "PBKS": ["punjab kings", "pbks", "kings xi punjab"],
    "RR": ["rajasthan royals", "rr"],
    "RCB": ["royal challengers bengaluru", "royal challengers bangalore", "rcb"],
    "SRH": ["sunrisers hyderabad", "srh", "deccan chargers"],
}


def matches_team(team_string: str, target_team_codes: list[str]) -> bool:
    """Check if a parsed team string matches any of our target team codes."""
    team_lower = team_string.lower()
    for code in target_team_codes:
        aliases = TEAM_ALIASES.get(code, [code.lower()])
        if any(alias in team_lower for alias in aliases):
            return True
    return False


def filter_matches(matches: list[dict], team_codes: list[str]) -> list[dict]:
    """Filter match list by team codes. Returns all if 'ALL' is passed."""
    if not team_codes or "ALL" in team_codes:
        return matches

    filtered = []
    for match in matches:
        if matches_team(match["team1"], team_codes) or matches_team(match["team2"], team_codes):
            filtered.append(match)
    return filtered


# CricAPI helpers ------------------------------------------------------------

def _api_get(endpoint: str, params: dict) -> dict:
    params = {**params, "apikey": API_KEY}
    response = requests.get(f"{BASE_URL}/{endpoint}", params=params, headers=HEADERS, timeout=15)
    response.raise_for_status()
    data = response.json()
    if data.get("status") != "success":
        raise RuntimeError(f"CricAPI /{endpoint} error: {data.get('reason', data)}")
    return data


def _find_ipl_series_id() -> str | None:
    keywords = ["IPL", "INDIAN PREMIER LEAGUE"]
    offset = 0
    while True:
        data = _api_get("series", {"offset": offset})
        items = data.get("data", [])
        if not items:
            break
        for series in items:
            name = series.get("name", "").upper()
            if YEAR in name and any(keyword in name for keyword in keywords):
                log.info(f"Found series: {series['name']} (id={series['id']})")
                return series["id"]
        offset += len(items)
    return None


def fetch_from_cricapi() -> list[dict] | None:
    if not API_KEY:
        log.warning("CRICAPI_KEY not set - skipping CricAPI")
        return None

    try:
        series_id = os.environ.get("SERIES_ID") or _find_ipl_series_id()
        if not series_id:
            log.warning("IPL series not found in CricAPI - will use fallback")
            return None
        log.info(f"Using series ID: {series_id}")

        data = _api_get("series_info", {"id": series_id})
        raw_matches = data.get("data", {}).get("matchList", [])
        matches = []
        for match in raw_matches:
            teams = match.get("teams", [])
            matches.append(
                {
                    "id": match.get("id", ""),
                    "team1": teams[0] if len(teams) > 0 else "TBD",
                    "team2": teams[1] if len(teams) > 1 else "TBD",
                    "venue": match.get("venue", "TBD"),
                    "dt_utc": match.get("dateTimeGMT", ""),
                    "source": "cricapi",
                }
            )
        log.info(f"CricAPI returned {len(matches)} matches")
        return matches or None
    except Exception as exc:
        log.error(f"CricAPI fetch failed: {exc}")
        return None


# Cricbuzz fallback ----------------------------------------------------------

_CRICBUZZ_DATE_TITLE_RE = re.compile(
    r"^[A-Z][a-z]{2},\s+[A-Z][a-z]{2}\s+\d{1,2}\s+20\d{2}$"
)


def _parse_cricbuzz_teams(title_attr: str) -> tuple[str, str] | None:
    """Extract teams from a match-card title like 'Team A vs Team B, 6th Match'."""
    title_attr = " ".join(title_attr.split())
    match = re.match(r"(.+?)\s+vs\s+(.+?)(?:,\s*.*)?$", title_attr, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).strip(), match.group(2).strip()


def _parse_cricbuzz_venue(link) -> str:
    """Extract the venue from the short match-summary span."""
    for span in link.find_all("span"):
        text = " ".join(span.stripped_strings)
        parts = re.split(r"\s*\u2022\s*", text, maxsplit=1)
        if len(parts) == 2 and parts[1].strip():
            return parts[1].strip()
        fallback = re.sub(
            r"^.*?(?:\bMatch\b|Qualifier\s+\d+|Eliminator|Final)\s*",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip(" -:")
        if fallback and fallback != text and "," in fallback:
            return fallback
    return "TBD"


def _parse_cricbuzz_gmt_datetime(card_text: str) -> datetime | None:
    """Parse 'Match starts at Apr 02, 14:00 GMT' into an IST-aware datetime."""
    match = re.search(
        r"Match starts at\s+([A-Za-z]{3})\s+(\d{1,2}),\s+(\d{1,2}:\d{2})\s+GMT",
        card_text,
        re.IGNORECASE,
    )
    if not match:
        return None

    month_abbr, day, time_str = match.groups()
    try:
        dt_utc = datetime.strptime(f"{YEAR} {month_abbr} {day} {time_str}", "%Y %b %d %H:%M")
    except ValueError:
        return None
    return pytz.utc.localize(dt_utc).astimezone(IST)


def _parse_cricbuzz_local_datetime(card_text: str, current_date_str: str | None) -> datetime | None:
    """Fallback when the card only exposes local time."""
    if not current_date_str:
        return None

    match = re.search(r"(\d{1,2}:\d{2}\s*(?:AM|PM))\s*\(LOCAL\)", card_text, re.IGNORECASE)
    if not match:
        return None

    try:
        dt_local = datetime.strptime(
            f"{current_date_str} {match.group(1).upper()}",
            "%a, %b %d %Y %I:%M %p",
        )
    except ValueError:
        return None
    return IST.localize(dt_local)


def _extract_balanced_json(source: str, start_idx: int) -> str | None:
    """Return a balanced JSON object substring starting at start_idx."""
    depth = 0
    in_string = False
    escaped = False

    for idx in range(start_idx, len(source)):
        char = source[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start_idx : idx + 1]

    return None


def _parse_cricbuzz_embedded_matches(page_html: str) -> list[dict]:
    """Read Cricbuzz's embedded Next.js data instead of brittle rendered DOM."""
    soup = BeautifulSoup(page_html, "html.parser")
    match_details = None

    for script in soup.find_all("script"):
        content = script.string or script.get_text()
        if not content or "matchesData" not in content or "self.__next_f.push" not in content:
            continue

        match = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)\s*$', content, re.DOTALL)
        if not match:
            continue

        try:
            decoded = json.loads(f'"{match.group(1)}"')
        except json.JSONDecodeError:
            continue

        start = decoded.find('{"matchesData":')
        if start == -1:
            continue

        payload_str = _extract_balanced_json(decoded, start)
        if not payload_str:
            continue

        try:
            payload = json.loads(payload_str)
        except json.JSONDecodeError:
            continue

        match_details = payload.get("matchesData", {}).get("matchDetails")
        if match_details:
            break

    if not match_details:
        return []

    matches = []
    seen_ids = set()

    for section in match_details:
        details_map = section.get("matchDetailsMap") or {}
        if str(details_map.get("seriesId", "")) != "9241":
            continue

        for entry in details_map.get("match", []):
            match_info = entry.get("matchInfo") or {}
            match_id = str(match_info.get("matchId", "")).strip()
            if not match_id or match_id in seen_ids:
                continue

            try:
                dt_ist = datetime.fromtimestamp(
                    int(match_info.get("startDate")) / 1000,
                    tz=pytz.utc,
                ).astimezone(IST)
            except (TypeError, ValueError, OSError):
                continue

            team1 = (match_info.get("team1") or {}).get("teamName", "TBD")
            team2 = (match_info.get("team2") or {}).get("teamName", "TBD")
            venue_info = match_info.get("venueInfo") or {}
            venue = ", ".join(
                part for part in [venue_info.get("city", "").strip(), venue_info.get("ground", "").strip()] if part
            ) or "TBD"

            matches.append(
                {
                    "id": f"cb-{match_id}",
                    "team1": team1,
                    "team2": team2,
                    "venue": venue,
                    "dt_ist": dt_ist,
                    "source": "cricbuzz",
                }
            )
            seen_ids.add(match_id)

    return matches


def fetch_from_cricbuzz() -> list[dict] | None:
    log.info(f"Fetching schedule from Cricbuzz: {CRICBUZZ_URL}")
    try:
        response = requests.get(CRICBUZZ_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.error(f"Cricbuzz fetch failed: {exc}")
        return None

    embedded_matches = _parse_cricbuzz_embedded_matches(response.text)
    if embedded_matches:
        log.info(f"Cricbuzz embedded data returned {len(embedded_matches)} matches")
        return embedded_matches

    soup = BeautifulSoup(response.text, "html.parser")
    matches = []
    current_date_str = None
    seen_hrefs = set()
    match_cards_seen = 0

    # Walk anchors in document order so each date header applies to the cards below it.
    for link in soup.find_all("a"):
        title_attr = " ".join(link.get("title", "").split())
        href = link.get("href", "")

        if title_attr and _CRICBUZZ_DATE_TITLE_RE.match(title_attr):
            current_date_str = title_attr
            continue

        if not href.startswith("/live-cricket-scores/"):
            continue

        match_cards_seen += 1
        if href in seen_hrefs:
            continue

        teams = _parse_cricbuzz_teams(title_attr)
        if not teams:
            continue
        team1, team2 = teams

        card_text = " ".join(link.stripped_strings)
        dt_ist = _parse_cricbuzz_gmt_datetime(card_text) or _parse_cricbuzz_local_datetime(
            card_text,
            current_date_str,
        )
        if not dt_ist:
            continue

        venue = _parse_cricbuzz_venue(link)
        href_parts = href.strip("/").split("/")
        match_id = href_parts[1] if len(href_parts) > 1 else re.sub(r"\W+", "-", href.strip("/"))

        matches.append(
            {
                "id": f"cb-{match_id}",
                "team1": team1,
                "team2": team2,
                "venue": venue,
                "dt_ist": dt_ist,
                "source": "cricbuzz",
            }
        )
        seen_hrefs.add(href)

    if matches:
        log.info(f"Cricbuzz returned {len(matches)} matches")
        return matches

    log.error(f"Could not parse any matches from Cricbuzz (found {match_cards_seen} candidate match cards)")
    return None


# ICS builder ----------------------------------------------------------------

def _to_ist(match: dict) -> datetime | None:
    if "dt_ist" in match:
        return match["dt_ist"]
    date_str = match.get("dt_utc", "")
    if not date_str:
        return None
    try:
        dt_utc = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt_utc.tzinfo is None:
            dt_utc = pytz.utc.localize(dt_utc)
        return dt_utc.astimezone(IST)
    except ValueError:
        return None


def build_calendar(matches: list[dict], calendar_name: str) -> Calendar:
    cal = Calendar()
    cal.add("prodid", f"-//IPL 2026 Schedule - {calendar_name}//ipl-calendar//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("method", "PUBLISH")
    cal.add("x-wr-calname", f"IPL 2026: {calendar_name}")
    cal.add("x-wr-timezone", "Asia/Kolkata")
    cal.add("x-wr-caldesc", f"IPL 2026 match schedule ({calendar_name}) - auto-updated daily")
    cal.add("x-published-ttl", "P1D")

    for match in matches:
        dt_start = _to_ist(match)
        if dt_start is None:
            continue

        team1 = match.get("team1", "TBD")
        team2 = match.get("team2", "TBD")
        venue = match.get("venue", "TBD")

        event = Event()
        event.add("uid", str(uuid.uuid5(uuid.NAMESPACE_URL, f"ipl2026-{match['id']}")))
        event.add("summary", f"IPL: {team1} vs {team2}")
        event.add("dtstart", dt_start)
        event.add("dtend", dt_start + timedelta(hours=4))
        event.add("location", venue)
        event.add(
            "description",
            (
                f"{team1} vs {team2}\n"
                f"Venue: {venue}\n"
                f"Kickoff: {dt_start.strftime('%I:%M %p IST')}\n"
                f"Source: {match.get('source', '?')}"
            ),
        )
        event.add("dtstamp", datetime.now(pytz.utc))
        event.add("status", "CONFIRMED")
        event.add("transp", "OPAQUE")
        cal.add_component(event)

    return cal


# Entry point ----------------------------------------------------------------

def main():
    # Attempt API fetch. Try/except block inside ensures safe fallback.
    matches = fetch_from_cricapi()
    if not matches:
        matches = fetch_from_cricbuzz()

    if not matches:
        log.error("Both CricAPI and Cricbuzz sources failed - cannot generate calendar")
        sys.exit(1)

    CALENDARS_DIR.mkdir(parents=True, exist_ok=True)

    # Output generation: Define combos here.
    # "ALL" dumps everything. A hyphen combines teams (e.g. "RCB-MI").
    calendars_to_build = [
        "ALL",
        "CSK",
        "DC",
        "GT",
        "KKR",
        "LSG",
        "MI",
        "PBKS",
        "RR",
        "RCB",
        "SRH",
    ]

    for combo_str in calendars_to_build:
        team_codes = combo_str.split("-")
        combo_matches = filter_matches(matches, team_codes)

        if not combo_matches:
            log.warning(f"No matches found for {combo_str}, skipping...")
            continue

        cal = build_calendar(combo_matches, calendar_name=combo_str)

        if combo_str == "ALL":
            output_path = CALENDARS_DIR / f"ipl_{YEAR}.ics"
        else:
            output_path = CALENDARS_DIR / f"ipl_{YEAR}_{combo_str.lower()}.ics"

        with open(output_path, "wb") as handle:
            handle.write(cal.to_ical())

        log.info(
            f"Written {output_path.relative_to(ROOT_DIR)} ({len(combo_matches)} matches, source: {combo_matches[0].get('source')})"
        )


if __name__ == "__main__":
    main()



