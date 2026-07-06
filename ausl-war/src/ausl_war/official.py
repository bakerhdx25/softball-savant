from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .io import read_json
from .normalize import (
    RunnerState,
    _advance_for_batter,
    _force_walk,
    apply_runner_clauses,
    batter_destination,
    classify_plate_appearance,
    outs_on_plate_appearance,
    parse_innings,
)


PERSON_KEY_ALIASES = {
    "aliaguliar": "aliaguilar",
    "corimcmillian": "corimcmillan",
    "dejamulipola": "dejahmulipola",
    "jailalassiter": "jalialassiter",
    "kaileywycoff": "kaileywyckoff",
    "odiccialexander": "odiccialexanderbennett",
    "paytongotshall": "paytongottshall",
    "paytongottshallmcmillan": "paytongottshall",
    "savannahjaquish": "sahvannajaquish",
    "sierrasacco": "sierrasaccoferrie",
}


def canonical_person_key(value: str) -> str:
    from .normalize import normalize_person_name

    key = normalize_person_name(value)
    return PERSON_KEY_ALIASES.get(key, key)


def _extract_next_object(html: str, key: str) -> dict[str, Any]:
    decoded_chunks = []
    pattern = re.compile(r'self\.__next_f\.push\(\[1,"((?:\\.|[^"\\])*)"\]\)')
    for match in pattern.finditer(html):
        try:
            decoded_chunks.append(json.loads(f'"{match.group(1)}"'))
        except json.JSONDecodeError:
            continue
    decoded = "".join(decoded_chunks)
    marker = decoded.find(f'"{key}"')
    if marker < 0:
        raise ValueError(f"Official game page does not contain {key}")
    start = decoded.find("{", marker)
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(decoded)):
        character = decoded[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                return json.loads(decoded[start : index + 1])
    raise ValueError(f"Official game page contains an incomplete {key} object")


SEASON_IDS = {2025: 270, 2026: 369}
POSITION_NUMBER = {
    1: "pitcher",
    2: "catcher",
    3: "first baseman",
    4: "second baseman",
    5: "third baseman",
    6: "shortstop",
    7: "left fielder",
    8: "center fielder",
    9: "right fielder",
}
POSITION_CODE = {
    "P": "pitcher", "C": "catcher", "1B": "first baseman", "2B": "second baseman",
    "3B": "third baseman", "SS": "shortstop", "LF": "left fielder",
    "CF": "center fielder", "RF": "right fielder",
}


def display_team(name: str, season: int) -> str:
    short = (name or "").removeprefix("AUSL ").strip()
    if season == 2025:
        return short
    return {
        "Bandits": "Chicago Bandits",
        "Blaze": "Carolina Blaze",
        "Cascade": "Portland Cascade",
        "Spark": "Oklahoma City Spark",
        "Talons": "Utah Talons",
        "Volts": "Texas Volts",
    }.get(short, short)


def official_stats(project_root: Path, snapshot_id: str, season: int) -> list[dict[str, Any]]:
    path = (
        project_root
        / "data"
        / "raw"
        / "official-stats"
        / snapshot_id
        / f"{season}.json"
    )
    payload = read_json(path)
    expected = SEASON_IDS[season]
    if int(payload.get("seasonId", -1)) != expected:
        raise ValueError(f"Official stats season mismatch: expected {expected}")
    return payload["stats"]


def completed_schedule(project_root: Path, snapshot_id: str, season: int) -> list[dict[str, Any]]:
    path = project_root / "data" / "raw" / "official-schedule" / snapshot_id / f"{season}.json"
    return [
        game
        for game in read_json(path)["games"]
        if game.get("recordStatus") == "Completed"
    ]


def team_run_totals(project_root: Path, snapshot_id: str, season: int) -> dict[str, int]:
    totals: dict[str, int] = {}
    for game in completed_schedule(project_root, snapshot_id, season):
        for competitor in game["competitors"]:
            team = display_team(competitor["name"], season)
            competitor_id = competitor.get("eventTeamId", competitor.get("competitorId"))
            is_home = int(competitor_id) == int(game["homeTeamId"])
            runs = game["homeTeamScore"] if is_home else game["awayTeamScore"]
            totals[team] = totals.get(team, 0) + int(runs or 0)
    return totals


def _position(value: str | None) -> str | None:
    parts = [part for part in (value or "").split("/") if part and part not in {"PH", "PR", "DP"}]
    return parts[0] if parts else None


def _official_event_type(action: str, narrative: str) -> str:
    classified = classify_plate_appearance(narrative or "")
    if classified != "unknown":
        return classified
    code = (action or "").upper().strip()
    for prefix, event_type in (
        ("HR", "home_run"), ("3B", "triple"), ("2B", "double"), ("1B", "single"),
        ("IBB", "intentional_walk"), ("BB", "walk"), ("HBP", "hit_by_pitch"),
        ("SF", "sacrifice_fly"), ("SH", "sacrifice_bunt"), ("SAC", "sacrifice_bunt"),
        ("CI", "catcher_interference"), ("FC", "fielders_choice"), ("E", "reached_on_error"),
    ):
        if code.startswith(prefix):
            return event_type
    if code.startswith(("KS", "KL", "K ", "KWP", "KPB")):
        return "dropped_third_reached" if "reached" in narrative.lower() else "strikeout"
    if "DP" in code:
        return "double_play"
    return "out" if code and code != "/" else "unknown"


def _people_and_aliases(box: dict[str, Any]) -> tuple[dict[int, str], list[str], list[tuple[str, str]]]:
    people: dict[int, str] = {}
    aliases: list[tuple[str, str]] = []
    for section in ("batting", "pitching"):
        for side in ("home", "away"):
            for player in (box.get(section, {}).get(side, {}) or {}).get("players", []):
                person_id = int(player["personId"])
                name = player["displayName"]
                people[person_id] = name
                first, _, last = name.partition(" ")
                aliases.append((f"{first[:1]} {last}", name))
                stat_name = player.get("statName") or ""
                if "," in stat_name:
                    surname, given = [part.strip() for part in stat_name.split(",", 1)]
                    aliases.append((f"{given.rstrip('.')} {surname}", name))
    aliases = sorted(set(aliases), key=lambda row: len(row[0]), reverse=True)
    return people, sorted(set(people.values()), key=len, reverse=True), aliases


def _expand_names(text: str, aliases: list[tuple[str, str]]) -> str:
    result = text or ""
    for alias, name in aliases:
        result = re.sub(rf"(?<![A-Za-z]){re.escape(alias)}(?![A-Za-z])", name, result, flags=re.I)
    return (
        result.replace(" advanced to first", " advances to 1st")
        .replace(" advanced to second", " advances to 2nd")
        .replace(" advanced to third", " advances to 3rd")
        .replace(" stole second", " steals 2nd")
        .replace(" stole third", " steals 3rd")
        .replace(" scored", " scores")
        .replace(" out at first", " out at 1st")
        .replace(" out at second", " out at 2nd")
        .replace(" out at third", " out at 3rd")
        .replace(" out at home", " out at home")
    )


def _lineups(box: dict[str, Any], season: int) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    teams = {int(row["eventTeamId"]): display_team(row["name"], season) for row in box["competitors"]}
    for side in ("home", "away"):
        section = box["batting"][side]
        team = teams[int(section["eventTeamId"])]
        active: dict[str, str] = {}
        for player in section.get("players", []):
            if player.get("isSub"):
                continue
            code = (player.get("position") or "").split("/", 1)[0]
            if code in POSITION_CODE:
                active[POSITION_CODE[code]] = player["displayName"]
        result[team] = active
    return result


def _apply_substitution(
    text: str,
    known_names: list[str],
    lineups: dict[str, dict[str, str]],
    player_teams: dict[str, str],
) -> None:
    low = text.lower()
    player = next((name for name in known_names if low.startswith(name.lower())), None)
    if not player:
        return
    match = re.search(r"\bto (p|c|1b|2b|3b|ss|lf|cf|rf)\b", low, re.I)
    if not match:
        return
    position = POSITION_CODE[match.group(1).upper()]
    active = lineups[player_teams[player]]
    for old_position, old_player in list(active.items()):
        if old_player == player:
            del active[old_position]
    active[position] = player


def _primary_position(action: str) -> str | None:
    code = re.sub(r"^(?:HR|3B|2B|1B|IBB|BB|HBP|SF|SH|SAC|CI|FC|E|KS|KL|KWP|KPB)\s*", "", (action or "").upper())
    match = re.search(r"[1-9]", code)
    return POSITION_NUMBER.get(int(match.group())) if match else None


def supplemental_normalized_events(
    project_root: Path,
    snapshot_id: str,
    supplemental_audit: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    schedules = {
        int(game["gameId"]): (season, game)
        for season in SEASON_IDS
        for game in completed_schedule(project_root, snapshot_id, season)
    }
    events: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    for audit_row in supplemental_audit:
        game_id = int(audit_row["official_game_id"])
        season, game = schedules[game_id]
        path = project_root / "data" / "raw" / "official-games" / snapshot_id / f"{game_id}.html"
        html = path.read_text(encoding="utf-8")
        box = _extract_next_object(html, "initialBoxScore")
        pbp = _extract_next_object(html, "playByPlayData")
        people, known_names, aliases = _people_and_aliases(box)
        teams = {int(row["eventTeamId"]): display_team(row["name"], season) for row in box["competitors"]}
        lineups = _lineups(box, season)
        player_teams = {
            player["displayName"]: teams[int(box["batting"][side]["eventTeamId"])]
            for side in ("home", "away")
            for player in box["batting"][side].get("players", [])
        }
        state = RunnerState.empty()
        current_half: tuple[int, str] | None = None
        score_by_team = {team: 0 for team in teams.values()}
        game_events = []
        state_errors = []
        expected_runs = int(game["homeTeamScore"] or 0) + int(game["awayTeamScore"] or 0)
        for play in pbp["plays"]:
            if int(play.get("playSeqno") or -1) < 0:
                continue
            inning = int(play["inning"])
            half = "top" if play.get("topBottomFlg") else "bottom"
            half_key = (inning, half)
            if half_key != current_half:
                state = RunnerState.empty()
                if inning >= 8:
                    state.runners[2] = "__placed_runner__"
                current_half = half_key
            batting_team = teams[int(play["offensiveTeamId"])]
            fielding_team = teams[int(play["defensiveTeamId"])]
            text = _expand_names(play.get("narrative") or "", aliases)
            _apply_substitution(text, known_names, lineups, player_teams)
            current_score = int(play.get("offensiveTeamScore") or 0)
            runs_scored = max(0, current_score - score_by_team[batting_team])
            score_by_team[batting_team] = current_score
            batter_id = play.get("batterId")
            pitcher_id = play.get("pitcherId")
            is_pa = batter_id is not None and pitcher_id is not None
            runner_only = not is_pa and any(
                phrase in text.lower()
                for phrase in (" steals ", "caught stealing", " advances to ", "wild pitch", "passed ball")
            )
            if not is_pa and not runner_only:
                continue
            before = state.snapshot()
            before_mask = state.mask()
            outs_before = int(play.get("outs") or 0)
            parsed_runs, runner_outs, actions = apply_runner_clauses(state, text, known_names)
            event_type = "runner_advance"
            batter = people.get(int(batter_id)) if batter_id is not None else None
            pitcher = people.get(int(pitcher_id)) if pitcher_id is not None else None
            if runner_only:
                low = text.lower()
                event_type = "caught_stealing" if "caught stealing" in low else "stolen_base" if " steals " in low else "wild_pitch" if "wild pitch" in low else "passed_ball" if "passed ball" in low else "runner_advance"
                outs_after = min(3, outs_before + runner_outs)
            else:
                event_type = _official_event_type(play.get("action") or "", text)
                if event_type in {"walk", "intentional_walk", "hit_by_pitch", "catcher_interference"}:
                    _force_walk(state)
                destination = batter_destination(event_type)
                explicit_batter = any(canonical_person_key(action["runner"]) == canonical_person_key(batter or "") for action in actions)
                if destination == 4 and not explicit_batter:
                    _, forced_actions = _advance_for_batter(state, destination)
                    actions.extend(forced_actions)
                    state.remove(batter or "")
                elif destination and not explicit_batter:
                    _, forced_actions = _advance_for_batter(state, destination)
                    actions.extend(forced_actions)
                    state.place(destination, batter or "")
                outs_after = min(3, outs_before + max(runner_outs, outs_on_plate_appearance(event_type, text)))
            primary_position = _primary_position(play.get("action") or "")
            fielder = lineups.get(fielding_team, {}).get(primary_position or "")
            if primary_position and fielder:
                text = f"{text} Fielded by {primary_position} {fielder}."
            for error in state.invariant_errors():
                state_errors.append({"play": play["playSeqno"], "error": error})
            game_events.append(
                {
                    "canonical_id": audit_row["canonical_id"],
                    "source_game_id": f"official-{game_id}",
                    "source_kind": "official_ausl_play_by_play",
                    "season": season,
                    "inning": inning,
                    "half": half,
                    "event_order": len(game_events) + 1,
                    "display_row_index": int(play["playSeqno"]),
                    "event_type": event_type,
                    "is_plate_appearance": is_pa,
                    "batting_team": batting_team,
                    "fielding_team": fielding_team,
                    "batter": batter,
                    "pitcher": pitcher,
                    "pitcher_key": canonical_person_key(pitcher or "") if pitcher else None,
                    "outs_before": outs_before,
                    "bases_before": before_mask,
                    "runners_before": before,
                    "outs_after": outs_after,
                    "bases_after": state.mask(),
                    "runners_after": state.snapshot(),
                    "runs_scored": runs_scored,
                    "runner_actions": actions,
                    "pitch_text": "",
                    "play_text": text,
                    "official_action": play.get("action"),
                }
            )
        events.extend(game_events)
        observed_runs = sum(row["runs_scored"] for row in game_events)
        audits.append(
            {
                "season": season,
                "official_game_id": game_id,
                "canonical_id": audit_row["canonical_id"],
                "events": len(game_events),
                "plate_appearances": sum(row["is_plate_appearance"] for row in game_events),
                "expected_runs": expected_runs,
                "observed_runs": observed_runs,
                "run_difference": observed_runs - expected_runs,
                "state_invariant_errors": state_errors,
                "state_invariant_error_count": len(state_errors),
            }
        )
    return events, audits


def supplemental_boxscore_rows(
    project_root: Path,
    snapshot_id: str,
    existing_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    existing_games = {row["canonical_id"] for row in existing_rows}
    rows: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []
    schedules = {
        int(game["gameId"]): (season, game)
        for season in SEASON_IDS
        for game in completed_schedule(project_root, snapshot_id, season)
    }
    pages = project_root / "data" / "raw" / "official-games" / snapshot_id
    for path in sorted(pages.glob("*.html")):
        game_id = int(path.stem)
        if game_id not in schedules:
            continue
        season, game = schedules[game_id]
        canonical_id = f"official-ausl-{season}-{game_id}"
        if canonical_id in existing_games:
            continue
        box = _extract_next_object(path.read_text(encoding="utf-8"), "initialBoxScore")
        game_rows = []
        for role, section in (("hitting", "batting"), ("pitching", "pitching")):
            for side in ("home", "away"):
                team_section = (box.get(section, {}).get(side, {}) or {})
                event_team_id = team_section.get("eventTeamId")
                team_record = next(
                    item for item in box["competitors"] if item["eventTeamId"] == event_team_id
                )
                team = display_team(team_record["name"], season)
                for player in team_section.get("players", []):
                    base = {
                        "canonical_id": canonical_id,
                        "source_game_id": f"official-{game_id}",
                        "season": season,
                        "role": role,
                        "team": team,
                        "player": player["displayName"],
                        "player_key": canonical_person_key(player["displayName"]),
                        "jersey_number": None,
                        "position": _position(player.get("position")),
                    }
                    if role == "hitting":
                        base.update(
                            {
                                "AB": int(player.get("ab") or 0),
                                "R": int(player.get("r") or 0),
                                "H": int(player.get("h") or 0),
                                "BB": int(player.get("bb") or 0),
                                "SO": int(player.get("so") or 0),
                            }
                        )
                    else:
                        ip = str(player.get("ip") or "0.0")
                        base.update(
                            {
                                "IP": ip,
                                "innings_decimal": parse_innings(ip),
                                "H": int(player.get("h") or 0),
                                "R": int(player.get("r") or 0),
                                "ER": int(player.get("er") or 0),
                                "BB": int(player.get("bb") or 0),
                                "SO": int(player.get("so") or 0),
                                "HR": int(player.get("hr") or 0),
                                "BF": int(player.get("bf") or 0),
                            }
                        )
                    game_rows.append(base)
        rows.extend(game_rows)
        audit.append(
            {
                "season": season,
                "official_game_id": game_id,
                "canonical_id": canonical_id,
                "boxscore_rows": len(game_rows),
                "home_runs": int(game["homeTeamScore"] or 0),
                "away_runs": int(game["awayTeamScore"] or 0),
            }
        )
    return rows, audit
