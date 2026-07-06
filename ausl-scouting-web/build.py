#!/usr/bin/env python3
"""Build the isolated AUSL digital scouting-report dataset."""

from __future__ import annotations

import json
import math
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

SITE_ROOT = Path(__file__).resolve().parent
WAR_ROOT = SITE_ROOT.parent / "ausl-war"
OUTPUT_ROOT = WAR_ROOT / "output"
SNAPSHOT_ID = "20260704T165430Z"
SNAPSHOT_ROOT = WAR_ROOT / "data" / "snapshots" / SNAPSHOT_ID

POSITION_SOURCES = {season: OUTPUT_ROOT / f"position_players_{season}.json" for season in (2025, 2026)}
PITCHER_SOURCES = {season: OUTPUT_ROOT / f"pitchers_{season}.json" for season in (2025, 2026)}
BASERUNNING_SOURCES = {season: OUTPUT_ROOT / f"baserunning_{season}.json" for season in (2025, 2026)}
ADVANCEMENT_SOURCES = {season: OUTPUT_ROOT / f"advancement_opportunities_{season}.json" for season in (2025, 2026)}
PA_SOURCE = OUTPUT_ROOT / "tto" / "plate_appearances.json"
TTO_SOURCE = OUTPUT_ROOT / "tto" / "pitcher_splits.json"
HEADSHOT_SOURCE = OUTPUT_ROOT / "headshots_2026.json"
PLACEHOLDER_HEADSHOT_SHA256 = {"ad69020650ba93a1da18e628bb62fa8032cdb4d51bf647ed85ff599da090495a"}
OFFICIAL_STATS_SOURCES = {season: WAR_ROOT / "data" / "raw" / "official-stats" / SNAPSHOT_ID / f"{season}.json" for season in (2025, 2026)}
OFFICIAL_GAME_HTML_ROOT = WAR_ROOT / "data" / "raw" / "official-games" / SNAPSHOT_ID
NORMALIZED_EVENTS_SOURCE = SNAPSHOT_ROOT / "normalized" / "events.json"
OFFICIAL_EVENTS_SOURCE = OUTPUT_ROOT / "official_supplemental_events.json"
BOX_SOURCE = SNAPSHOT_ROOT / "normalized" / "player_game_boxscore.json"
DESTINATION = SITE_ROOT / "data" / "scouting-data.json"
PERIOD_DESTINATIONS = {
    "2026": DESTINATION,
    "2025": SITE_ROOT / "data" / "scouting-data-2025.json",
    "2025-2026": SITE_ROOT / "data" / "scouting-data-2025-2026.json",
}
HEADSHOT_DESTINATION = SITE_ROOT / "assets" / "headshots"

TEAM_META = {
    "bandits": {"name": "Chicago Bandits", "short": "Bandits", "code": "CHI", "color": "#43B6E6", "ink": "#102C3A", "logo": "https://resource.auprosports.com/prod/franchises/1/1-icon.svg"},
    "blaze": {"name": "Carolina Blaze", "short": "Blaze", "code": "CAR", "color": "#FAA21B", "ink": "#3A2600", "logo": "https://resource.auprosports.com/prod/franchises/2/2-icon.svg"},
    "cascade": {"name": "Portland Cascade", "short": "Cascade", "code": "POR", "color": "#A6192E", "ink": "#FFFFFF", "logo": "https://resource.auprosports.com/prod/franchises/6/6-icon.svg"},
    "spark": {"name": "Oklahoma City Spark", "short": "Spark", "code": "OKC", "color": "#194F90", "ink": "#FFFFFF", "logo": "https://resource.auprosports.com/prod/franchises/5/5-icon.svg"},
    "talons": {"name": "Utah Talons", "short": "Talons", "code": "UTA", "color": "#2A4F3A", "ink": "#FFFFFF", "logo": "https://resource.auprosports.com/prod/franchises/3/3-icon.svg"},
    "volts": {"name": "Texas Volts", "short": "Volts", "code": "TEX", "color": "#440099", "ink": "#FFFFFF", "logo": "https://resource.auprosports.com/prod/franchises/4/4-icon.svg"},
}

FIELD_WIDTH, FIELD_HEIGHT = 800, 620
FIELD_HOME = (400, 570)
OUTFIELD_RADIUS = (330, 480)
INFIELD_RADIUS = (182.1875, 265)


def field_point(radius: float | tuple[float, float], angle: float) -> list[int]:
    x_radius, y_radius = radius if isinstance(radius, tuple) else (radius, radius)
    radians = math.radians(angle)
    return [round(FIELD_HOME[0] + x_radius * math.cos(radians)), round(FIELD_HOME[1] - y_radius * math.sin(radians))]


def field_arc(radius: float | tuple[float, float], start: float, end: float, steps: int = 18) -> list[list[int]]:
    return [field_point(radius, start + (end - start) * index / steps) for index in range(steps + 1)]


def outfield_zone(start: float, end: float) -> list[list[int]]:
    return field_arc(OUTFIELD_RADIUS, start, end) + list(reversed(field_arc(INFIELD_RADIUS, start, end, 10)))


def infield_zone(start: float, end: float) -> list[list[int]]:
    return [list(FIELD_HOME)] + field_arc(INFIELD_RADIUS, start, end, 10)


ZONE_MAP = {
    "Left Field": outfield_zone(145, 108.333),
    "Center Field": outfield_zone(108.333, 71.667),
    "Right Field": outfield_zone(71.667, 35),
    "Third Base": infield_zone(145, 117.5),
    "Shortstop": infield_zone(117.5, 90),
    "Second Base": infield_zone(90, 62.5),
    "First Base": infield_zone(62.5, 35),
}

ZONE_LABEL_ANCHORS = {
    "Left Field": field_point((270, 360), 126.667),
    "Center Field": field_point((265, 360), 90),
    "Right Field": field_point((270, 360), 53.333),
    "Third Base": [304, 409],
    "Shortstop": [366, 361],
    "Second Base": [434, 361],
    "First Base": [496, 409],
}

POSITION_ALIASES = (
    ("pitcher", "Pitcher"), ("catcher", "Catcher"),
    ("first baseman", "First Base"), ("first base", "First Base"),
    ("second baseman", "Second Base"), ("second base", "Second Base"),
    ("third baseman", "Third Base"), ("third base", "Third Base"),
    ("shortstop", "Shortstop"), ("left fielder", "Left Field"),
    ("left field", "Left Field"), ("center fielder", "Center Field"),
    ("center field", "Center Field"), ("right fielder", "Right Field"),
    ("right field", "Right Field"),
)
ALL_COUNTS = tuple(f"{balls}-{strikes}" for balls in range(4) for strikes in range(3))
HITTER_PA_PER_TEAM_GAME = 2.0
PITCHER_IP_PER_TEAM_GAME = 1.0
FIELDER_QUALIFIER_CHANCES = 20


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def number(value: Any) -> float:
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else 0.0
    except (TypeError, ValueError):
        return 0.0


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def official_game_date(value: str | None) -> str:
    """Return the AUSL schedule date instead of the UTC calendar date."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except ValueError:
        return value[:10]


def innings_from_outs(outs: int) -> float:
    return float(f"{outs // 3}.{outs % 3}")


def player_key(value: str | None) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    return "".join(character for character in normalized if character.isalnum()).lower()


def team_key(value: str | None) -> str:
    normalized = (value or "").lower().strip()
    for key in TEAM_META:
        if normalized.endswith(key):
            return key
    return normalized.replace("ausl ", "").replace(" ", "-")


def main_team(row: dict[str, Any]) -> str:
    teams = row.get("teams") or []
    return team_key(teams[-1] if teams else row.get("team"))


def result_label(event_type: str) -> str:
    return {
        "single": "1B", "double": "2B", "triple": "3B", "home_run": "HR",
        "walk": "BB", "intentional_walk": "IBB", "hit_by_pitch": "HBP",
        "strikeout": "K", "dropped_third_out": "K", "dropped_third_reached": "K / Reach",
        "reached_on_error": "ROE", "fielders_choice": "FC", "double_play": "DP",
        "sacrifice_bunt": "SAC", "sacrifice_fly": "SF", "out": "Out",
        "infield_fly": "Out", "catcher_interference": "CI",
    }.get(event_type, event_type.replace("_", " ").title())


def get_play_location_search_text(play_text: str) -> str:
    match = re.search(
        r"\b(?:singles?|doubles?|triples?|homers?|hits?|grounds?(?:\s+(?:out|into))?|"
        r"lines?\s+out|flies?\s+out|pops?\s+out|bunts?|sacrifices?|reaches|walks?|strikes?\s+out)\b",
        play_text,
    )
    return play_text[match.start():] if match else play_text


def field_location(play_text: str) -> str | None:
    text = get_play_location_search_text((play_text or "").lower())
    mentions = []
    for alias, canonical in POSITION_ALIASES:
        for match in re.finditer(rf"\b{re.escape(alias)}\b", text):
            prefix = text[:match.start()]
            preceded_by_to = bool(re.search(r"\bto\s*$", prefix))
            preceded_by_throw = preceded_by_to and bool(re.search(r"\b(?:relay|throw|throws|threw|thrown)\s+to\s*$", prefix))
            mentions.append((match.start(), canonical, preceded_by_to, preceded_by_throw))
    mentions.sort(key=lambda item: item[0])
    primary = next((mention for mention in mentions if not mention[2]), None)
    if primary:
        return primary[1]
    target = next((mention for mention in mentions if not mention[3]), None)
    return target[1] if target else None


def contact_type(play_text: str) -> str:
    text = (play_text or "").lower()
    if "bunt" in text or "sacrifices" in text and "sacrifice fly" not in text:
        return "Bunt"
    if "ground" in text:
        return "Ground"
    if "line" in text:
        return "Line"
    if "pop" in text or "infield fly" in text:
        return "Pop"
    if "fly" in text or "flies" in text:
        return "Fly"
    return "Other"


def parse_pitch_sequence(pitch_text: str) -> list[dict[str, Any]]:
    balls = strikes = 0
    pitches: list[dict[str, Any]] = []
    for raw in re.split(r",\s*", pitch_text or ""):
        action = raw.replace("\u00a0", " ").strip().rstrip(".")
        lowered = action.lower()
        if not action or lowered.startswith("lineup changed"):
            continue
        count = f"{balls}-{strikes}"
        is_ball = lowered.startswith("ball ") or lowered == "ball"
        swing = "foul" in lowered or "swinging" in lowered or "in play" in lowered
        called = "looking" in lowered and "strike" in lowered
        if not (is_ball or swing or called):
            continue
        pitches.append({"count": count, "action": action, "swing": swing, "called": called, "strike": not is_ball})
        if is_ball:
            balls = min(4, balls + 1)
        elif "foul" in lowered:
            strikes = strikes + 1 if strikes < 2 else strikes
        elif "strike" in lowered and strikes < 3:
            strikes += 1
    return pitches


def batting_from_pas(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pa = len(rows)
    ab = int(sum(number(row.get("AB_value")) for row in rows))
    hits = int(sum(number(row.get("H_value")) for row in rows))
    total_bases = int(sum(number(row.get("TB_value")) for row in rows))
    obp_num = sum(number(row.get("OBP_num_value")) for row in rows)
    obp_den = sum(number(row.get("OBP_den_value")) for row in rows)
    return {
        "PA": pa, "AB": ab, "H": hits,
        "1B": sum(row.get("event_type") == "single" for row in rows),
        "2B": sum(row.get("event_type") == "double" for row in rows),
        "3B": sum(row.get("event_type") == "triple" for row in rows),
        "HR": sum(row.get("event_type") == "home_run" for row in rows),
        "BB": int(sum(number(row.get("BB_value")) for row in rows)),
        "HBP": int(sum(number(row.get("HBP_value")) for row in rows)),
        "SO": int(sum(number(row.get("SO_value")) for row in rows)),
        "SF": int(sum(number(row.get("SF_value")) for row in rows)),
        "BA": ratio(hits, ab), "OBP": ratio(obp_num, obp_den), "SLG": ratio(total_bases, ab),
        "OPS": (ratio(obp_num, obp_den) or 0) + (ratio(total_bases, ab) or 0),
    }


def official_player_map(path: Path) -> dict[str, dict[str, Any]]:
    output = {}
    for row in load(path)["stats"]:
        key = player_key(f"{row.get('firstName', '')}{row.get('lastName', '')}")
        batting = (row.get("battingStats") or [None])[0]
        pitching = (row.get("pitchingStats") or [None])[0]
        fielding = row.get("fieldingStats") or []
        positions = []
        for item in fielding:
            position = str(item.get("position") or "").strip()
            if position and position not in positions:
                positions.append(position)
        primary = ((row.get("primaryPosition") or {}).get("shortDescription") or "").strip()
        if primary and primary not in positions:
            positions.insert(0, primary)
        chances = sum(number(item.get("totalChances")) for item in fielding)
        output[key] = {
            "name": f"{row.get('firstName', '')} {row.get('lastName', '')}".strip(),
            "jersey": row.get("uniformNumberDisplay"), "batsThrows": row.get("batsThrows"),
            "team": team_key(row.get("franchiseName")), "positions": positions,
            "batting": batting, "pitching": pitching,
            "fielding": {
                "errors": int(sum(number(item.get("errors")) for item in fielding)),
                "putOuts": int(sum(number(item.get("putOuts")) for item in fielding)),
                "assists": int(sum(number(item.get("assists")) for item in fielding)),
                "totalChances": int(chances),
                "fieldingPct": ratio(
                    sum(number(item.get("putOuts")) + number(item.get("assists")) for item in fielding), chances
                ),
                "stolenBasesAllowed": int(sum(number(item.get("stolenBases")) for item in fielding if item.get("position") == "C")),
                "caughtStealing": int(sum(number(item.get("caughtStealing")) for item in fielding if item.get("position") == "C")),
            },
        }
    return output


def combine_advanced_rows(paths: list[Path], kind: str) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for path in paths:
        for row in load(path):
            groups[row["player_key"]].append(row)
    output = []
    for key, rows in groups.items():
        if len(rows) == 1:
            output.append(rows[0]); continue
        merged: dict[str, Any] = {"player_key": key, "player": rows[-1].get("player"), "teams": sorted({team for row in rows for team in row.get("teams", [])})}
        numeric_fields = {field for row in rows for field, item in row.items() if isinstance(item, (int, float)) and field not in {"wOBA", "ERA", "FIP", "ERA_minus_FIP", "RA7", "OBP"}}
        for field in numeric_fields:
            merged[field] = sum(number(row.get(field)) for row in rows)
        if kind == "position":
            pa = sum(number(row.get("PA")) for row in rows)
            merged["wOBA"] = ratio(sum(number(row.get("wOBA"))*number(row.get("PA")) for row in rows), pa)
            merged["OBP"] = ratio(sum(number(row.get("OBP"))*number(row.get("PA")) for row in rows), pa)
        elif kind == "pitcher":
            ip = sum(number(row.get("IP")) for row in rows)
            bf = sum(number(row.get("FIP_BF")) for row in rows)
            merged["IP"] = ip
            merged["ERA"] = 7 * sum(number(row.get("ER")) for row in rows) / ip if ip else None
            merged["FIP"] = ratio(sum(number(row.get("FIP"))*number(row.get("FIP_BF")) for row in rows), bf)
            merged["ERA_minus_FIP"] = None if merged["ERA"] is None or merged["FIP"] is None else merged["ERA"]-merged["FIP"]
        output.append(merged)
    return output


def merge_official_maps(maps: list[dict[str, dict[str, Any]]], identity: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    keys = set().union(*(item.keys() for item in maps))
    output: dict[str, dict[str, Any]] = {}
    batting_fields = ("plateAppearances","atBat","hits","doubles","triples","homeRuns","baseonBalls","hitByPitch","strikeOuts","stolenBasesAttempts","stolenBases","caughtStealing","sacrificeFly")
    pitching_fields = ("appearances","gamesStarted","hitsAllowed","baseOnBalls","strikeOuts","numberOfPitches","strikes","wins","losses","earnedRuns")
    for key in keys:
        rows = [item[key] for item in maps if key in item]
        base = identity.get(key) or rows[-1]
        batting_rows = [row.get("batting") or {} for row in rows if row.get("batting")]
        pitching_rows = [row.get("pitching") or {} for row in rows if row.get("pitching")]
        batting = None
        if batting_rows:
            batting = {field: sum(number(row.get(field)) for row in batting_rows) for field in batting_fields}
            ab, hits = batting["atBat"], batting["hits"]
            batting["battingAverage"] = ratio(hits, ab)
            obp_den = ab+batting["baseonBalls"]+batting["hitByPitch"]+batting["sacrificeFly"]
            batting["onBasePercentage"] = ratio(hits+batting["baseonBalls"]+batting["hitByPitch"], obp_den)
            total_bases = hits-batting["doubles"]-batting["triples"]-batting["homeRuns"]+2*batting["doubles"]+3*batting["triples"]+4*batting["homeRuns"]
            batting["sluggingPercentage"] = ratio(total_bases, ab)
            batting["opsPercentage"] = (batting["onBasePercentage"] or 0)+(batting["sluggingPercentage"] or 0)
        pitching = None
        if pitching_rows:
            pitching = {field: sum(number(row.get(field)) for row in pitching_rows) for field in pitching_fields}
            outs = sum(round(number(row.get("inningsPitched"))//1*3 + round(number(row.get("inningsPitched"))%1*10)) for row in pitching_rows)
            innings = outs/3
            pitching["inningsPitched"] = innings
            pitching["earnedRunAverage"] = 7*pitching["earnedRuns"]/innings if innings else None
            pitching["whip"] = ratio(pitching["hitsAllowed"]+pitching["baseOnBalls"], innings)
        fielding_rows = [row.get("fielding") or {} for row in rows]
        chances = sum(number(row.get("totalChances")) for row in fielding_rows)
        fielding = {field: int(sum(number(row.get(field)) for row in fielding_rows)) for field in ("errors","putOuts","assists","totalChances","stolenBasesAllowed","caughtStealing")}
        fielding["fieldingPct"] = ratio(fielding["putOuts"]+fielding["assists"], chances)
        output[key] = {**base, "batting": batting, "pitching": pitching, "fielding": fielding}
    return output


def times_through_order_splits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups = {"1": [], "2": [], "3+": []}
    for row in rows:
        encounter = int(number(row.get("same_game_matchup_number")))
        groups["1" if encounter <= 1 else "2" if encounter == 2 else "3+"].append(row)
    output = []
    for encounter, group in groups.items():
        stats = batting_from_pas(group) if group else {"PA":0,"AB":0,"H":0,"BB":0,"SO":0,"BA":None,"OBP":None,"SLG":None,"OPS":None}
        output.append({"encounter":encounter,"PA":stats["PA"],"games":len({row["canonical_id"] for row in group}),"AVG":stats.get("BA"),"OBP":stats.get("OBP"),"SLG":stats.get("SLG"),"OPS":stats.get("OPS"),"K_pct":ratio(stats.get("SO",0),stats["PA"]),"BB_pct":ratio(stats.get("BB",0),stats["PA"]),"wOBA":ratio(sum(number(row.get("wOBA_num_value")) for row in group),sum(number(row.get("wOBA_den_value")) for row in group))})
    return output


def official_pitching_game_boxes() -> dict[tuple[str, str], dict[str, Any]]:
    """Read the captured official game box scores embedded in each game page."""
    boxes: dict[tuple[str, str], dict[str, Any]] = {}
    pattern = re.compile(
        r'\{\\"personId\\":\d+,\\"eventTeamId\\":\d+,\\"displayName\\":\\"([^\"]+)\\"'
        r'[^{}]*?\\"position\\":\\"P\\"[^{}]*?\\"h\\":(\d+),\\"r\\":(\d+),\\"er\\":(\d+),'
        r'\\"bb\\":(\d+),\\"so\\":(\d+),\\"hr\\":(\d+),\\"ab\\":(\d+),\\"bf\\":(\d+),'
        r'\\"np\\":(\d+)[^{}]*?\\"ip\\":\\"([0-9.]+)\\"'
    )
    if not OFFICIAL_GAME_HTML_ROOT.is_dir():
        return boxes
    for path in OFFICIAL_GAME_HTML_ROOT.glob("*.html"):
        game_id = f"official-ausl-2026-{path.stem}"
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in pattern.finditer(text):
            name, hits, runs, earned, walks, strikeouts, homers, at_bats, batters_faced, pitches, innings = match.groups()
            boxes[(player_key(name), game_id)] = {
                "innings_decimal": float(innings), "H": int(hits), "R": int(runs), "ER": int(earned),
                "BB": int(walks), "SO": int(strikeouts), "HR": int(homers), "AB": int(at_bats),
                "BF": int(batters_faced), "Pitches": int(pitches), "source": "official_game_box",
            }
    return boxes


def original_hitting_stats(official: dict[str, Any] | None, derived: dict[str, Any], bunt_attempts: int, gb_pct: float | None) -> dict[str, Any]:
    source = (official or {}).get("batting") or {}
    pa = int(number(source.get("plateAppearances"))) or derived["PA"]
    ab = int(number(source.get("atBat"))) or derived["AB"]
    hits = int(number(source.get("hits"))) or derived["H"]
    doubles = int(number(source.get("doubles"))) or derived["2B"]
    triples = int(number(source.get("triples"))) or derived["3B"]
    homers = int(number(source.get("homeRuns"))) or derived["HR"]
    walks = int(number(source.get("baseonBalls"))) or derived["BB"]
    hbp = int(number(source.get("hitByPitch"))) or derived["HBP"]
    strikeouts = int(number(source.get("strikeOuts"))) or derived["SO"]
    ba = source.get("battingAverage") if source else derived["BA"]
    obp = source.get("onBasePercentage") if source else derived["OBP"]
    slg = source.get("sluggingPercentage") if source else derived["SLG"]
    ops = source.get("opsPercentage") if source else derived["OPS"]
    sba = int(number(source.get("stolenBasesAttempts")))
    return {
        "PA": pa, "AB": ab, "H": hits, "K": strikeouts, "BB": walks, "HBP": hbp,
        "HR": homers, "XBH": doubles + triples + homers, "SBA": sba,
        "SB": int(number(source.get("stolenBases"))), "CS": int(number(source.get("caughtStealing"))),
        "Bunts": bunt_attempts, "BA": ba, "OBP": obp, "SLG": slg, "OPS": ops,
        "K_pct": ratio(strikeouts, pa), "BB_pct": ratio(walks, pa), "GB_pct": gb_pct,
    }


def original_pitching_stats(official: dict[str, Any] | None, advanced: dict[str, Any] | None, pitches: list[dict[str, Any]]) -> dict[str, Any] | None:
    source = (official or {}).get("pitching") or {}
    innings = number(source.get("inningsPitched")) or number((advanced or {}).get("IP"))
    if innings <= 0:
        return None
    hits = int(number(source.get("hitsAllowed"))) or int(number((advanced or {}).get("H_allowed")))
    walks = int(number(source.get("baseOnBalls"))) or int(number((advanced or {}).get("BB_allowed")))
    strikeouts = int(number(source.get("strikeOuts"))) or int(number((advanced or {}).get("SO_pitching")))
    total_pitches = int(number(source.get("numberOfPitches"))) or len(pitches)
    strikes = int(number(source.get("strikes"))) or sum(pitch["strike"] for pitch in pitches)
    era = source.get("earnedRunAverage") if source else (advanced or {}).get("ERA")
    whip = source.get("whip") if source else None
    if whip is None:
        whip = ratio(hits + walks, innings)
    return {
        "App": int(number(source.get("appearances"))) or int(number((advanced or {}).get("G"))),
        "GS": int(number(source.get("gamesStarted"))) or int(number((advanced or {}).get("GS"))),
        "IP": innings, "ERA": era, "WHIP": whip,
        "SO": strikeouts, "BB": walks, "H": hits,
        "SO7": 7 * strikeouts / innings, "BB7": 7 * walks / innings,
        "S_pct": ratio(strikes, total_pitches), "Pitches": total_pitches, "Strikes": strikes,
        "W": int(number(source.get("wins"))), "L": int(number(source.get("losses"))),
    }


def aggregate_matchups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[row["pitcher_key"]].append(row)
    output = []
    for key, group in groups.items():
        stats = batting_from_pas(group)
        output.append({"pitcherKey": key, "pitcher": Counter(row["pitcher"] for row in group).most_common(1)[0][0], **stats})
    return sorted(output, key=lambda row: (-row["PA"], row["pitcher"]))


def prior_series_splits(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {"0": [], "1": [], "2+": []}
    for row in rows:
        prior = int(number(row.get("prior_series_game_matchups")))
        groups["0" if prior == 0 else "1" if prior == 1 else "2+"].append(row)
    output = []
    for encounter, group in groups.items():
        stats = batting_from_pas(group) if group else {"PA": 0, "AB": 0, "H": 0, "BB": 0, "SO": 0, "AVG": None, "OBP": None, "SLG": None, "OPS": None}
        pa = stats["PA"]
        output.append({
            "encounter": encounter, "PA": pa, "games": len({row["canonical_id"] for row in group}),
            "AVG": stats.get("BA"), "OBP": stats.get("OBP"), "SLG": stats.get("SLG"), "OPS": stats.get("OPS"),
            "K_pct": ratio(stats.get("SO", 0), pa), "BB_pct": ratio(stats.get("BB", 0), pa),
            "wOBA": ratio(sum(number(row.get("wOBA_num_value")) for row in group), sum(number(row.get("wOBA_den_value")) for row in group)),
        })
    return output


def hitter_game_logs(rows: list[dict[str, Any]], game_context: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    games: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        games[row["canonical_id"]].append(row)
    output = []
    for game_rows in games.values():
        stats = batting_from_pas(game_rows)
        first = game_rows[0]
        context = game_context.get(first["canonical_id"], {})
        output.append({
            "gameId": first["canonical_id"], "date": context.get("date") or official_game_date(first.get("game_start")), "opponent": TEAM_META[team_key(first.get("fielding_team"))]["short"],
            "result": context.get(team_key(first.get("batting_team")), ""),
            **stats,
            "plateAppearances": [{"inning": row.get("inning"), "half": row.get("half"), "pitcher": row.get("pitcher"), "result": result_label(row["event_type"]), "sequence": row.get("pitch_text"), "play": row.get("play_text")} for row in sorted(game_rows, key=lambda item: number(item.get("event_order")))],
        })
    return sorted(output, key=lambda row: row["date"], reverse=True)


def pitcher_game_logs(rows: list[dict[str, Any]], pitching_box: dict[tuple[str, str], dict[str, Any]], game_context: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    games: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        games[(row["pitcher_key"], row["canonical_id"])].append(row)
    output = []
    for (key, game_id), game_rows in games.items():
        first = game_rows[0]
        box = pitching_box.get((key, game_id), {})
        context = game_context.get(game_id, {})
        outs = sum(max(0, int(number(row.get("outs_after"))) - int(number(row.get("outs_before")))) for row in game_rows)
        runs = sum(int(number(row.get("runs_scored"))) for row in game_rows)
        output.append({
            "gameId": game_id, "date": context.get("date") or official_game_date(first.get("game_start")), "opponent": TEAM_META[team_key(first.get("batting_team"))]["short"],
            "result": context.get(team_key(first.get("fielding_team")), ""),
            "IP": box.get("innings_decimal") if box else innings_from_outs(outs), "H": int(number(box.get("H"))) if box else sum(row["event_type"] in {"single", "double", "triple", "home_run"} for row in game_rows),
            "R": int(number(box.get("R"))) if box else runs, "ER": int(number(box.get("ER"))) if box else runs,
            "BB": int(number(box.get("BB"))) if box else sum(number(row.get("BB_value")) for row in game_rows),
            "SO": int(number(box.get("SO"))) if box else sum(number(row.get("SO_value")) for row in game_rows),
            "BF": len(game_rows),
        })
    return sorted(output, key=lambda row: row["date"], reverse=True)


def percentile(value: float, population: list[float], lower_is_better: bool = False) -> int | None:
    if value is None or not population:
        return None
    less = sum(item < value for item in population)
    equal = sum(item == value for item in population)
    score = 100 * (less + 0.5 * equal) / len(population)
    if lower_is_better:
        score = 100 - score
    return max(1, min(99, round(score)))


def metric_context(player: dict[str, Any], eligible: list[dict[str, Any]], getter, lower_is_better: bool) -> dict[str, Any]:
    value = getter(player)
    ordered = sorted(eligible, key=getter, reverse=not lower_is_better)
    rank = next(index for index, item in enumerate(ordered, start=1) if item["key"] == player["key"])
    return {
        "value": value,
        "percentile": percentile(value, [getter(item) for item in eligible], lower_is_better),
        "rank": rank,
        "of": len(eligible),
    }


def build_period(period: str, base_teams: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    seasons = (2026,) if period == "2026" else (2025,) if period == "2025" else (2025, 2026)
    position_rows = combine_advanced_rows([POSITION_SOURCES[season] for season in seasons], "position")
    pitcher_rows = combine_advanced_rows([PITCHER_SOURCES[season] for season in seasons], "pitcher")
    baserunning_rows = combine_advanced_rows([BASERUNNING_SOURCES[season] for season in seasons], "baserunning")
    advancement_rows = [row for season in seasons for row in load(ADVANCEMENT_SOURCES[season])]
    all_plate_appearances = load(PA_SOURCE)
    plate_appearances = [row for row in all_plate_appearances if row.get("season") in seasons]
    headshots = load(HEADSHOT_SOURCE)
    current_official = official_player_map(OFFICIAL_STATS_SOURCES[2026])
    official_maps = [official_player_map(OFFICIAL_STATS_SOURCES[season]) for season in seasons]
    official_players = current_official if seasons == (2026,) else official_maps[0] if len(official_maps) == 1 else merge_official_maps(official_maps, current_official)
    box_rows = [row for row in load(BOX_SOURCE) if row.get("season") in seasons]

    all_events = [row for row in load(NORMALIZED_EVENTS_SOURCE) if row.get("season") in seasons]
    all_events += [row for row in load(OFFICIAL_EVENTS_SOURCE) if row.get("season") in seasons]
    game_scores: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    game_teams: dict[str, set[str]] = defaultdict(set)
    game_starts: dict[str, str] = {}
    for event in all_events:
        game_id = event["canonical_id"]
        batting = team_key(event.get("batting_team")); fielding = team_key(event.get("fielding_team"))
        game_teams[game_id].update((batting, fielding))
        game_scores[game_id][batting] += int(number(event.get("runs_scored")))
        game_starts.setdefault(game_id, event.get("game_start") or "")
    team_game_counts = {key: sum(key in teams for teams in game_teams.values()) for key in TEAM_META}
    game_context: dict[str, dict[str, Any]] = {}
    for game_id, teams in game_teams.items():
        context: dict[str, Any] = {"date": official_game_date(game_starts.get(game_id))}
        for team in teams:
            opponent = next(iter(teams - {team}), None)
            team_runs = game_scores[game_id].get(team, 0); opponent_runs = game_scores[game_id].get(opponent, 0)
            result = "W" if team_runs > opponent_runs else "L" if team_runs < opponent_runs else "T"
            context[team] = f"{result} {team_runs}-{opponent_runs}"
        game_context[game_id] = context

    position_by_key = {row["player_key"]: row for row in position_rows}
    pitcher_by_key = {row["player_key"]: row for row in pitcher_rows}
    baserunning_by_key = {row["player_key"]: row for row in baserunning_rows}
    pa_by_batter: dict[str, list[dict[str, Any]]] = defaultdict(list)
    pa_by_pitcher: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in plate_appearances:
        pa_by_batter[row["batter_key"]].append(row)
        pa_by_pitcher[row["pitcher_key"]].append(row)
    all_pa_by_pitcher = pa_by_pitcher
    pitching_box = {(row["player_key"], row["canonical_id"]): row for row in box_rows if row.get("role") == "pitching"}
    pitching_box.update(official_pitching_game_boxes())

    advancement_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in advancement_rows:
        if row.get("role") == "runner":
            advancement_by_key[row["player_key"]].append(row)

    current_position_rows = load(POSITION_SOURCES[2026])
    current_pitcher_rows = load(PITCHER_SOURCES[2026])
    current_source_by_key = {row["player_key"]: row for row in current_position_rows}
    current_source_by_key.update({row["player_key"]: row for row in current_pitcher_rows})
    current_keys = {row["player_key"] for row in current_position_rows} | {row["player_key"] for row in current_pitcher_rows} | set(current_official)
    keys = sorted(set(position_by_key) | set(pitcher_by_key) | set(official_players) | current_keys)
    players = []
    for key in keys:
        advanced_batting = position_by_key.get(key)
        advanced_pitching = pitcher_by_key.get(key)
        official = official_players.get(key)
        identity = current_official.get(key) or official
        source = advanced_batting or advanced_pitching or {}
        current_source = current_source_by_key.get(key) or {}
        team = (identity or {}).get("team") or main_team(current_source) or main_team(source)
        if team not in TEAM_META:
            continue
        batter_pas = sorted(pa_by_batter.get(key, []), key=lambda row: (row.get("game_start") or "", number(row.get("event_order"))), reverse=True)
        pitcher_pas = pa_by_pitcher.get(key, [])
        all_pitcher_pitches = [pitch for row in pitcher_pas for pitch in parse_pitch_sequence(row.get("pitch_text") or "")]

        spray_counts = {location: 0 for location in (*ZONE_MAP.keys(), "Pitcher", "Catcher")}
        batted_balls = []
        bunts = grounds = balls_in_play = infield_grounds = 0
        approach = {count: {"count": count, "pitches": 0, "swings": 0, "calledStrikes": 0} for count in ALL_COUNTS}
        for pa in batter_pas:
            for pitch in parse_pitch_sequence(pa.get("pitch_text") or ""):
                bucket = approach.get(pitch["count"])
                if bucket:
                    bucket["pitches"] += 1
                    bucket["swings"] += int(pitch["swing"])
                    bucket["calledStrikes"] += int(pitch["called"])
            contact = contact_type(pa.get("play_text") or "")
            location = field_location(pa.get("play_text") or "")
            if contact != "Other":
                balls_in_play += 1
                bunts += int(contact == "Bunt")
                grounds += int(contact == "Ground")
                infield_grounds += int(contact == "Ground" and location in {"Pitcher", "Catcher", "First Base", "Second Base", "Third Base", "Shortstop"})
            if location and contact != "Other":
                spray_counts[location] = spray_counts.get(location, 0) + 1
                batted_balls.append({"location": location, "contact": contact, "result": result_label(pa["event_type"]), "date": (pa.get("game_start") or "")[:10], "pitcher": pa.get("pitcher"), "play": pa.get("play_text")})
        for row in approach.values():
            total = row["pitches"]
            row["swingPct"] = ratio(row["swings"], total)
            row["calledStrikePct"] = ratio(row["calledStrikes"], total)

        derived = batting_from_pas(batter_pas)
        original_batting = original_hitting_stats(official, derived, bunts, ratio(grounds, balls_in_play)) if derived["PA"] or (official or {}).get("batting") else None
        if original_batting and original_batting["PA"] <= 0:
            original_batting = None
        original_pitching = original_pitching_stats(official, advanced_pitching, all_pitcher_pitches)
        runner_rows = advancement_by_key.get(key, [])
        extra_taken = sum(row["action"] in {"advance", "score"} and number(row["destination"]) - number(row["start_base"]) >= 2 for row in runner_rows)
        advancement_outs = sum(row["action"] == "out" for row in runner_rows)
        baserunning = baserunning_by_key.get(key) or {}

        headshot_entry = headshots.get(key) or {}
        local_headshot = None
        source_path = OUTPUT_ROOT / str(headshot_entry.get("local_path") or "")
        if source_path.is_file() and headshot_entry.get("sha256") not in PLACEHOLDER_HEADSHOT_SHA256:
            HEADSHOT_DESTINATION.mkdir(parents=True, exist_ok=True)
            destination = HEADSHOT_DESTINATION / source_path.name
            shutil.copy2(source_path, destination)
            local_headshot = f"assets/headshots/{destination.name}"

        players.append({
            "key": key, "name": (identity or {}).get("name") or current_source.get("player") or source.get("player") or key,
            "jersey": (identity or {}).get("jersey"), "batsThrows": (identity or {}).get("batsThrows"),
            "team": team, "positions": (identity or {}).get("positions") or [], "headshot": local_headshot, "currentRoster": key in current_keys,
            "hitting": original_batting, "pitching": original_pitching,
            "fielding": (official or {}).get("fielding"),
            "advancedHitting": {field: (advanced_batting or {}).get(field) for field in ("wOBA", "wRAA", "position_war", "offensive_war", "defensive_war", "baserunning_runs", "range_runs", "throwing_runs", "fielding_opportunities", "arm_opportunities")} if advanced_batting else None,
            "advancedPitching": {field: (advanced_pitching or {}).get(field) for field in ("FIP", "ERA_minus_FIP", "pitcher_war", "pitching_war", "pitcher_defense_war", "batters_faced_from_play_by_play")} if advanced_pitching else None,
            "spray": {"counts": spray_counts, "total": sum(spray_counts.values()), "balls": batted_balls},
            "approach": [approach[count] for count in ALL_COUNTS],
            "hittingGameLogs": hitter_game_logs(batter_pas, game_context),
            "pitchingGameLogs": pitcher_game_logs(pitcher_pas, pitching_box, game_context),
            "matchups": aggregate_matchups(batter_pas), "tto": times_through_order_splits(pitcher_pas),
            "seriesExposure": prior_series_splits(all_pa_by_pitcher.get(key, [])),
            "smallBall": {"stolenBaseAttempts": (original_batting or {}).get("SBA", 0), "bunts": bunts, "infieldGroundBalls": infield_grounds, "groundBalls": grounds},
            "baserunning": {
                "opportunities": len(runner_rows), "extraBasesTaken": extra_taken,
                "firstToThird": sum(row["start_base"] == 1 and row["destination"] == 3 and row["action"] == "advance" for row in runner_rows),
                "secondToHome": sum(row["start_base"] == 2 and row["destination"] == 4 and row["action"] == "score" for row in runner_rows),
                "firstToHome": sum(row["start_base"] == 1 and row["destination"] == 4 and row["action"] == "score" for row in runner_rows),
                "advancementOuts": advancement_outs, "runs": baserunning.get("baserunning_runs"),
            },
            "percentiles": {"hitting": None, "pitching": None},
        })

    active_game_counts = [games for games in team_game_counts.values() if games]
    qualifier_games = round(sum(active_game_counts)/len(active_game_counts)) if active_game_counts else 0
    hitter_qualifier = {key: math.ceil(HITTER_PA_PER_TEAM_GAME * qualifier_games) for key in TEAM_META}
    pitcher_qualifier = {key: PITCHER_IP_PER_TEAM_GAME * qualifier_games for key in TEAM_META}
    eligible_hitters = [player for player in players if player.get("hitting") and number(player["hitting"]["PA"]) >= hitter_qualifier[player["team"]]]
    eligible_pitchers = [player for player in players if player.get("pitching") and number(player["pitching"]["IP"]) >= pitcher_qualifier[player["team"]]]
    hitter_metrics = {
        "wOBA": (lambda p: number((p.get("advancedHitting") or {}).get("wOBA")), False),
        "BB%": (lambda p: number(p["hitting"].get("BB_pct")), False),
        "K%": (lambda p: number(p["hitting"].get("K_pct")), True),
        "HR rate": (lambda p: ratio(number(p["hitting"].get("HR")), number(p["hitting"].get("PA"))) or 0, False),
        "Baserunning": (lambda p: number((p.get("advancedHitting") or {}).get("baserunning_runs")), False),
        "Range": (lambda p: number((p.get("advancedHitting") or {}).get("range_runs")), False),
        "Arm": (lambda p: number((p.get("advancedHitting") or {}).get("throwing_runs")), False),
        "Position WAR": (lambda p: number((p.get("advancedHitting") or {}).get("position_war")), False),
    }
    pitcher_metrics = {
        "ERA": (lambda p: number(p["pitching"].get("ERA")), True),
        "FIP": (lambda p: number((p.get("advancedPitching") or {}).get("FIP")), True),
        "WHIP": (lambda p: number(p["pitching"].get("WHIP")), True),
        "K/7": (lambda p: number(p["pitching"].get("SO7")), False),
        "BB/7": (lambda p: number(p["pitching"].get("BB7")), True),
        "Pitcher WAR": (lambda p: number((p.get("advancedPitching") or {}).get("pitcher_war")), False),
    }
    for player in players:
        if player in eligible_hitters:
            player["percentiles"]["hitting"] = {label: metric_context(player, eligible_hitters, getter, lower) for label, (getter, lower) in hitter_metrics.items()}
        if player in eligible_pitchers:
            player["percentiles"]["pitching"] = {label: metric_context(player, eligible_pitchers, getter, lower) for label, (getter, lower) in pitcher_metrics.items()}
        player["qualifiers"] = {
            "hittingPA": hitter_qualifier[player["team"]],
            "pitchingIP": pitcher_qualifier[player["team"]],
            "fieldingChances": FIELDER_QUALIFIER_CHANCES,
        }

    league_approach = []
    for count in ALL_COUNTS:
        rows = [row for player in players for row in player["approach"] if row["count"] == count]
        pitches = sum(row["pitches"] for row in rows)
        league_approach.append({"count": count, "pitches": pitches, "swingPct": ratio(sum(row["swings"] for row in rows), pitches), "calledStrikePct": ratio(sum(row["calledStrikes"] for row in rows), pitches)})

    players_by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for player in players:
        players_by_team[player["team"]].append(player)
    teams = []
    for key, meta in TEAM_META.items():
        roster = [player for player in players_by_team.get(key, []) if player.get("currentRoster")]
        games = [game_id for game_id, team_set in game_teams.items() if key in team_set]
        wins = losses = ties = runs_for = runs_against = 0
        for game_id in games:
            opponents = game_teams[game_id] - {key}
            opponent = next(iter(opponents), None)
            team_runs = game_scores[game_id].get(key, 0); opponent_runs = game_scores[game_id].get(opponent, 0)
            runs_for += team_runs; runs_against += opponent_runs
            wins += int(team_runs > opponent_runs); losses += int(team_runs < opponent_runs); ties += int(team_runs == opponent_runs)
        hitters = [player for player in roster if player.get("hitting") and number(player["hitting"]["PA"]) > 0]
        pitchers = [player for player in roster if player.get("pitching") and number(player["pitching"]["IP"]) > 0]
        defensive_war = sum(number((player.get("advancedHitting") or {}).get("defensive_war")) for player in roster)
        staff_ip = sum(number(player["pitching"]["IP"]) for player in pitchers)
        staff_er = sum(number((official_players.get(player["key"], {}).get("pitching") or {}).get("earnedRuns")) for player in pitchers)
        catch_sb = sum(number((player.get("fielding") or {}).get("stolenBasesAllowed")) for player in roster)
        catch_cs = sum(number((player.get("fielding") or {}).get("caughtStealing")) for player in roster)
        defenders = [player for player in roster if number((player.get("advancedHitting") or {}).get("fielding_opportunities")) >= 10]
        teams.append({
            "key": key, **meta, "games": len(games), "record": {"wins": wins, "losses": losses, "ties": ties},
            "roster": [player["key"] for player in sorted(roster, key=lambda item: (-number((item.get("hitting") or {}).get("PA")), item["name"]))],
            "summary": {
                "runs": runs_for, "runsAllowed": runs_against, "runsPerGame": ratio(runs_for, len(games)),
                "ERA": 7 * staff_er / staff_ip if staff_ip else None, "defensiveWAR": defensive_war,
                "OPS": ratio(sum(number(player["hitting"]["OPS"]) * number(player["hitting"]["PA"]) for player in hitters), sum(number(player["hitting"]["PA"]) for player in hitters)),
            },
            "rankings": {},
            "leaders": {
                "hitters": [player["key"] for player in sorted(hitters, key=lambda item: (-number((item.get("advancedHitting") or {}).get("wOBA")), -number(item["hitting"]["PA"])))[:6]],
                "pitchers": [player["key"] for player in sorted(pitchers, key=lambda item: (-number((item.get("advancedPitching") or {}).get("pitcher_war")), -number(item["pitching"]["IP"])))[:6]],
                "smallBall": [player["key"] for player in sorted(hitters, key=lambda item: (-(item["smallBall"]["stolenBaseAttempts"] + item["smallBall"]["bunts"] + item["smallBall"]["infieldGroundBalls"]), item["name"]))[:6]],
                "baserunners": [player["key"] for player in sorted(hitters, key=lambda item: (-number(item["baserunning"]["runs"]), -item["baserunning"]["extraBasesTaken"]))[:6]],
                "defendersBest": [player["key"] for player in sorted(defenders, key=lambda item: (-number((item.get("advancedHitting") or {}).get("defensive_war")), item["name"]))[:4]],
                "defendersWorst": [player["key"] for player in sorted(defenders, key=lambda item: (number((item.get("advancedHitting") or {}).get("defensive_war")), item["name"]))[:4]],
                "sprayOverview": [player["key"] for player in sorted(hitters, key=lambda item: -number(item["hitting"]["PA"]))[:12]],
            },
            "catching": {"stolenBasesAllowed": int(catch_sb), "caughtStealing": int(catch_cs), "attempts": int(catch_sb + catch_cs), "caughtPct": ratio(catch_cs, catch_sb + catch_cs)},
            "pdf": f"output/pdf/{key}-2026-scouting-report-v5{'-2025-2026' if period == '2025-2026' else ''}.pdf" if period != "2025" else None,
        })

    rank_specs = {
        "record": (lambda team: ratio(team["record"]["wins"], team["games"]) or 0, True),
        "runsPerGame": (lambda team: number(team["summary"]["runsPerGame"]), True),
        "ERA": (lambda team: number(team["summary"]["ERA"]), False),
        "OPS": (lambda team: number(team["summary"]["OPS"]), True),
    }
    for label, (getter, descending) in rank_specs.items():
        ordered = sorted(teams, key=getter, reverse=descending)
        for index, team in enumerate(ordered, start=1):
            team["rankings"][label] = index

    if base_teams is not None:
        base_by_key = {team["key"]: team for team in base_teams}
        for team in teams:
            base = base_by_key[team["key"]]
            for field in ("games", "record", "summary", "rankings"):
                team[field] = base[field]

    payload = {
        "meta": {
            "season": 2026, "period": period, "periodLabel": "2025-26" if period == "2025-2026" else period, "snapshot": SNAPSHOT_ID, "generatedAt": datetime.now(timezone.utc).isoformat(),
            "games": len(game_teams), "plateAppearances": len(plate_appearances),
            "hitterQualifierRate": HITTER_PA_PER_TEAM_GAME, "pitcherQualifierRate": PITCHER_IP_PER_TEAM_GAME,
            "fielderQualifierChances": FIELDER_QUALIFIER_CHANCES,
            "sourceNote": "Captured AUSL, official AUSL, and GameChanger data through the local research snapshot.",
        },
        "field": {"image": "assets/field-clean-v2.svg", "width": FIELD_WIDTH, "height": FIELD_HEIGHT, "zones": ZONE_MAP, "labelAnchors": ZONE_LABEL_ANCHORS},
        "leagueApproach": league_approach, "teams": teams, "players": players,
    }
    destination = PERIOD_DESTINATIONS[period]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    return payload


def build() -> dict[str, Any]:
    payload_2026 = build_period("2026")
    build_period("2025", payload_2026["teams"])
    build_period("2025-2026", payload_2026["teams"])
    return payload_2026


if __name__ == "__main__":
    result = build()
    print(f"Built {len(PERIOD_DESTINATIONS)} period datasets with {len(result['teams'])} teams.")
