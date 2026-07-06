from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime
from itertools import groupby
from pathlib import Path
from typing import Any, Iterable

import certifi
import numpy as np

from .io import read_json, write_json
from .normalize import classify_plate_appearance, normalize_person_name
from .war import _batting_denominator, _obp_numerator, derive_woba_constants


OFFICIAL_SCHEDULE_URL = "https://theausl.com/data/scheduleApiData_{season_id}.json"
OFFICIAL_SEASON_IDS = {2025: 270, 2026: 369}
HIT_EVENTS = {"single", "double", "triple", "home_run"}
WALK_EVENTS = {"walk", "intentional_walk"}
STRIKEOUT_EVENTS = {"strikeout", "dropped_third_out", "dropped_third_reached"}
AB_EXCLUSIONS = {
    "walk",
    "intentional_walk",
    "hit_by_pitch",
    "sacrifice_fly",
    "sacrifice_bunt",
    "catcher_interference",
}
PERSON_KEY_ALIASES = {
    "aliaguliar": "aliaguilar",
    "corimcmillian": "corimcmillan",
    "dejamulipola": "dejahmulipola",
    "jailalassiter": "jalialassiter",
    "kaileywycoff": "kaileywyckoff",
    "odiccialexander": "odiccialexanderbennett",
    "paytongotshall": "paytongottshall",
    "savannahjaquish": "sahvannajaquish",
    "sierrasacco": "sierrasaccoferrie",
}
PERSON_DISPLAY_NAMES = {
    "odiccialexanderbennett": "Odicci Alexander-Bennett",
    "paytongottshall": "Payton Gottshall",
}


def canonical_person_key(value: str) -> str:
    key = normalize_person_name(value)
    return PERSON_KEY_ALIASES.get(key, key)


def _team_key(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]", "", (value or "").lower())
    for nickname in ("bandits", "blaze", "cascade", "spark", "talons", "volts"):
        if normalized.endswith(nickname):
            return nickname
    return normalized.removeprefix("ausl")


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def _iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _download_official_schedules(project_root: Path, snapshot_id: str) -> dict[int, dict[str, Any]]:
    destination = project_root / "data" / "raw" / "official-schedule" / snapshot_id
    destination.mkdir(parents=True, exist_ok=True)
    schedules: dict[int, dict[str, Any]] = {}
    manifest_rows = []
    for season, season_id in OFFICIAL_SEASON_IDS.items():
        path = destination / f"{season}.json"
        if not path.exists():
            request = urllib.request.Request(
                OFFICIAL_SCHEDULE_URL.format(season_id=season_id),
                headers={"User-Agent": "AUSL-TTO-Research/1.0"},
            )
            context = __import__("ssl").create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, timeout=30, context=context) as response:
                payload = response.read()
            path.write_bytes(payload)
        payload = path.read_bytes()
        schedules[season] = json.loads(payload)
        manifest_rows.append(
            {
                "season": season,
                "season_id": season_id,
                "url": OFFICIAL_SCHEDULE_URL.format(season_id=season_id),
                "file": path.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    write_json(
        destination / "manifest.json",
        {"snapshot_id": snapshot_id, "sources": manifest_rows},
    )
    return schedules


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


def _download_official_game_pages(
    project_root: Path, snapshot_id: str, games: list[dict[str, Any]]
) -> dict[int, str]:
    destination = project_root / "data" / "raw" / "official-games" / snapshot_id
    destination.mkdir(parents=True, exist_ok=True)
    pages = {}
    manifest = []
    for game in sorted(games, key=lambda row: int(row["gameId"])):
        game_id = int(game["gameId"])
        path = destination / f"{game_id}.html"
        url = f"https://theausl.com/game/{game_id}/"
        if not path.exists():
            request = urllib.request.Request(url, headers={"User-Agent": "AUSL-TTO-Research/1.0"})
            context = __import__("ssl").create_default_context(cafile=certifi.where())
            with urllib.request.urlopen(request, timeout=45, context=context) as response:
                payload = response.read()
            path.write_bytes(payload)
        payload = path.read_bytes()
        pages[game_id] = payload.decode("utf-8")
        manifest.append(
            {
                "game_id": game_id,
                "url": url,
                "file": path.name,
                "bytes": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    write_json(destination / "manifest.json", {"snapshot_id": snapshot_id, "sources": manifest})
    return pages


def _official_event_type(action: str, narrative: str) -> str:
    classified = classify_plate_appearance(narrative or "")
    if classified != "unknown":
        return classified
    code = (action or "").upper().strip()
    if code.startswith("HR"):
        return "home_run"
    if code.startswith("3B"):
        return "triple"
    if code.startswith("2B"):
        return "double"
    if code.startswith("1B"):
        return "single"
    if code.startswith("IBB"):
        return "intentional_walk"
    if code.startswith("BB"):
        return "walk"
    if code.startswith("HBP"):
        return "hit_by_pitch"
    if code.startswith(("KS", "KL", "K ", "KWP", "KPB")):
        return "dropped_third_reached" if "reached" in (narrative or "").lower() else "strikeout"
    if code.startswith("SF"):
        return "sacrifice_fly"
    if code.startswith(("SH", "SAC")):
        return "sacrifice_bunt"
    if code.startswith("CI"):
        return "catcher_interference"
    if "DP" in code:
        return "double_play"
    if code.startswith("FC"):
        return "fielders_choice"
    if code.startswith("E"):
        return "reached_on_error"
    if code:
        return "out"
    return "unknown"


def parse_official_game_pas(
    game: dict[str, Any], html: str, canonical_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    play_by_play = _extract_next_object(html, "playByPlayData")
    boxscore = _extract_next_object(html, "initialBoxScore")
    people: dict[int, str] = {}
    for section in ("batting", "pitching"):
        for side in ("home", "away"):
            for player in (boxscore.get(section, {}).get(side, {}) or {}).get("players", []):
                people[int(player["personId"])] = player["displayName"]
    teams = {int(row["eventTeamId"]): row["name"] for row in boxscore["competitors"]}
    expected_bf = sum(
        int((boxscore.get("pitching", {}).get(side, {}) or {}).get("totals", {}).get("bf") or 0)
        for side in ("home", "away")
    )
    expected_pitching = {
        key: sum(
            int((boxscore.get("pitching", {}).get(side, {}) or {}).get("totals", {}).get(key) or 0)
            for side in ("home", "away")
        )
        for key in ("h", "bb", "so", "hr")
    }
    rows = []
    unknown = []
    for play in play_by_play["plays"]:
        if play.get("batterId") is None or play.get("pitcherId") is None:
            continue
        batter_id = int(play["batterId"])
        pitcher_id = int(play["pitcherId"])
        if batter_id not in people or pitcher_id not in people:
            raise ValueError(f"Official game {game['gameId']} has an unmapped batter or pitcher ID")
        event_type = _official_event_type(play.get("action") or "", play.get("narrative") or "")
        if event_type == "unknown":
            unknown.append({"play": play["playSeqno"], "action": play.get("action"), "narrative": play.get("narrative")})
        batting_team = teams[int(play["offensiveTeamId"])]
        fielding_team = teams[int(play["defensiveTeamId"])]
        rows.append(
            {
                "canonical_id": canonical_id,
                "source_game_id": f"official-{game['gameId']}",
                "source_kind": "official_ausl_play_by_play",
                "season": 2025 if game["seasonId"] == OFFICIAL_SEASON_IDS[2025] else 2026,
                "inning": int(play["inning"]),
                "half": "top" if play.get("topBottomFlg") else "bottom",
                "event_order": int(play["playSeqno"]),
                "display_row_index": int(play["playSeqno"]),
                "event_type": event_type,
                "is_plate_appearance": True,
                "batting_team": batting_team,
                "fielding_team": fielding_team,
                "batter": people[batter_id],
                "pitcher": people[pitcher_id],
                "pitcher_key": canonical_person_key(people[pitcher_id]),
                "pitcher_original": people[pitcher_id],
                "pitcher_attribution_ambiguous": False,
                "pitcher_attribution_method": "official_pitcher_id",
                "outs_before": None,
                "outs_after": play.get("outs"),
                "bases_before": None,
                "bases_after": None,
                "runners_before": {},
                "runners_after": {},
                "runs_scored": None,
                "runner_actions": [],
                "pitch_text": "",
                "play_text": play.get("narrative") or "",
                "official_action": play.get("action"),
            }
        )
    if unknown:
        raise ValueError(f"Unknown official PA outcomes in game {game['gameId']}: {unknown[:5]}")
    if len(rows) != expected_bf:
        raise ValueError(
            f"Official game {game['gameId']} PA count {len(rows)} does not equal boxscore BF {expected_bf}"
        )
    observed_pitching = {
        "h": sum(row["event_type"] in HIT_EVENTS for row in rows),
        "bb": sum(row["event_type"] in WALK_EVENTS for row in rows),
        "so": sum(row["event_type"] in STRIKEOUT_EVENTS for row in rows),
        "hr": sum(row["event_type"] == "home_run" for row in rows),
    }
    if observed_pitching != expected_pitching:
        raise ValueError(
            f"Official game {game['gameId']} classified totals {observed_pitching} "
            f"do not match pitching boxscore {expected_pitching}"
        )
    return rows, {
        "official_game_id": int(game["gameId"]),
        "plate_appearances": len(rows),
        "boxscore_batters_faced": expected_bf,
        "unknown_outcomes": len(unknown),
        "classified_totals_match_boxscore": True,
    }


def _official_teams(game: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(_team_key(row.get("name", "")) for row in game.get("competitors", [])))


def _canonical_teams(game: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted(_team_key(name) for name in game["team_names"]))


def _scores(game: dict[str, Any], official: bool) -> tuple[int, ...] | None:
    values = (
        [game.get("homeTeamScore"), game.get("awayTeamScore")]
        if official
        else list((game.get("score") or {}).values())
    )
    if len(values) != 2 or any(value is None for value in values):
        return None
    return tuple(sorted(int(value) for value in values))


def match_official_games(
    canonical_games: list[dict[str, Any]], schedules: dict[int, dict[str, Any]]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    official = [game for schedule in schedules.values() for game in schedule["games"]]
    matches: dict[str, dict[str, Any]] = {}
    audit = []
    for game in canonical_games:
        if game.get("status") != "completed":
            continue
        game_date = _iso(game["start_ts"]).date()
        candidates = [
            row
            for row in official
            if _official_teams(row) == _canonical_teams(game)
            and abs((game_date - _iso(row["gameDateIso"]).date()).days) <= 1
            and row.get("recordStatus") == "Completed"
        ]
        exact_score = [row for row in candidates if _scores(row, True) == _scores(game, False)]
        if len(exact_score) == 1:
            selected, method = exact_score[0], "teams_date_score"
        elif candidates:
            distances = {
                row["gameId"]: abs((_iso(game["start_ts"]) - _iso(row["gameDateIso"])).total_seconds())
                for row in candidates
            }
            nearest = [row for row in candidates if distances[row["gameId"]] == min(distances.values())]
            if len(nearest) != 1:
                raise ValueError(
                    f"Official schedule time match is not unique for {game['canonical_id']}: "
                    f"{[row.get('gameId') for row in nearest]}"
                )
            selected, method = nearest[0], "teams_datetime_nearest_score_disagreement"
        else:
            raise ValueError(
                f"Official schedule match is not unique for {game['canonical_id']}: "
                f"{[row.get('gameId') for row in candidates]}"
            )
        matches[game["canonical_id"]] = selected
        audit.append(
            {
                "canonical_id": game["canonical_id"],
                "season": game["season"],
                "official_game_id": selected["gameId"],
                "match_method": method,
                "canonical_score": list(_scores(game, False) or ()),
                "official_score": list(_scores(selected, True) or ()),
                "official_venue": selected.get("venue", {}).get("name"),
            }
        )
    return matches, audit


def assign_series_ids(official_matches: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    regular_groups: dict[tuple[int, tuple[str, ...], str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    postseason_groups: dict[
        tuple[int, tuple[str, ...], str, int], list[tuple[str, dict[str, Any]]]
    ] = defaultdict(list)
    result: dict[str, dict[str, Any]] = {}
    for canonical_id, game in official_matches.items():
        season = 2025 if game["seasonId"] == OFFICIAL_SEASON_IDS[2025] else 2026
        if game.get("gameTypeLk") == "PS" or game.get("seriesId") is not None:
            postseason_groups[
                (
                    season,
                    _official_teams(game),
                    game.get("seriesType") or "postseason",
                    int(game.get("seriesId") or 0),
                )
            ].append((canonical_id, game))
            continue
        venue = game.get("venue", {}).get("name") or "unknown-venue"
        regular_groups[(season, _official_teams(game), venue)].append((canonical_id, game))

    for (season, teams, venue), rows in regular_groups.items():
        rows.sort(key=lambda item: _iso(item[1]["gameDateIso"]))
        cluster: list[tuple[str, dict[str, Any]]] = []
        clusters: list[list[tuple[str, dict[str, Any]]]] = []
        for item in rows:
            if cluster:
                gap = (_iso(item[1]["gameDateIso"]).date() - _iso(cluster[-1][1]["gameDateIso"]).date()).days
                if gap > 4:
                    clusters.append(cluster)
                    cluster = []
            cluster.append(item)
        if cluster:
            clusters.append(cluster)
        for members in clusters:
            first_date = _iso(members[0][1]["gameDateIso"]).date().isoformat()
            series_id = f"{season}-rs-{'-'.join(teams)}-{_slug(venue)}-{first_date}"
            for number, (canonical_id, _) in enumerate(members, 1):
                result[canonical_id] = {
                    "series_id": series_id,
                    "series_game_number": number,
                    "series_source": "official_teams_venue_date_cluster",
                }
    for (season, teams, series_type, official_series_id), rows in postseason_groups.items():
        rows.sort(key=lambda item: _iso(item[1]["gameDateIso"]))
        series_id = f"{season}-ps-{'-'.join(teams)}-{_slug(series_type)}-{official_series_id}"
        for inferred_number, (canonical_id, game) in enumerate(rows, 1):
            result[canonical_id] = {
                "series_id": series_id,
                "series_game_number": int(game.get("seriesGameNumber") or inferred_number),
                "series_source": (
                    "official_postseason_series_id"
                    if game.get("seriesGameNumber")
                    else "official_postseason_chronology"
                ),
            }
    return result


def _explicit_pitcher(text: str, names: list[str]) -> str | None:
    low = (text or "").lower()
    for name in sorted(names, key=len, reverse=True):
        if f"{name.lower()} pitching" in low:
            return name
    return None


def _pitcher_change_hint(text: str, names: list[str]) -> str | None:
    low = (text or "").lower()
    for name in sorted(names, key=len, reverse=True):
        if f"{name.lower()} in for pitcher" in low or f"{name.lower()} in at pitcher" in low:
            return name
    return None


def _reconstruct_team_pitchers(
    events: list[dict[str, Any]], pitcher_rows: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    names = [row["player"] for row in pitcher_rows]
    name_index = {name: index for index, name in enumerate(names)}
    targets = tuple(round(float(row["innings_decimal"]) * 3) for row in pitcher_rows)
    blocks = []
    for _, group in groupby(events, key=lambda event: event["display_row_index"]):
        rows = list(group)
        play_text = " ".join(row.get("play_text", "") for row in rows)
        pitch_text = " ".join(row.get("pitch_text", "") for row in rows)
        blocks.append(
            {
                "events": rows,
                "outs": sum(row["outs_after"] - row["outs_before"] for row in rows),
                "explicit": _explicit_pitcher(play_text, names),
                "hint": _pitcher_change_hint(pitch_text, names),
                "old": rows[-1].get("pitcher"),
            }
        )

    states: dict[tuple[tuple[int, ...], int], tuple[int, list[tuple[int, ...]]]] = {
        (tuple(0 for _ in names), -1): (0, [tuple()])
    }
    for block in blocks:
        next_states: dict[tuple[tuple[int, ...], int], tuple[int, list[tuple[int, ...]]]] = {}
        candidates: Iterable[int] = (
            [name_index[block["explicit"]]] if block["explicit"] else range(len(names))
        )
        for (used, previous), (cost, paths) in states.items():
            for candidate in candidates:
                updated = list(used)
                updated[candidate] += block["outs"]
                if updated[candidate] > targets[candidate]:
                    continue
                added_cost = 0 if previous in (-1, candidate) else 10
                if block["hint"] and names[candidate] != block["hint"]:
                    added_cost += 2
                if block["old"] and normalize_person_name(names[candidate]) != normalize_person_name(block["old"]):
                    added_cost += 1
                key = (tuple(updated), candidate)
                candidate_cost = cost + added_cost
                candidate_paths = [path + (candidate,) for path in paths]
                if key not in next_states or candidate_cost < next_states[key][0]:
                    next_states[key] = (candidate_cost, candidate_paths)
                elif candidate_cost == next_states[key][0]:
                    next_states[key][1].extend(candidate_paths)
        states = next_states
        if not states:
            raise ValueError("No feasible pitcher attribution path")

    exact = [(value, key) for key, value in states.items() if key[0] == targets]
    if not exact:
        raise ValueError(f"No attribution path reconciles pitcher outs {targets}")
    best_cost = min(value[0] for value, _ in exact)
    best_paths = [path for value, _ in exact if value[0] == best_cost for path in value[1]]
    primary = best_paths[0]
    output = []
    ambiguous_blocks = 0
    changed_pas = 0
    for block_index, (block, pitcher_index) in enumerate(zip(blocks, primary)):
        possible = {path[block_index] for path in best_paths}
        ambiguous = len(possible) > 1
        ambiguous_blocks += int(ambiguous)
        for event in block["events"]:
            corrected = dict(event)
            corrected["pitcher_original"] = event.get("pitcher")
            corrected["pitcher"] = names[pitcher_index]
            corrected["pitcher_key"] = canonical_person_key(names[pitcher_index])
            corrected["pitcher_attribution_ambiguous"] = ambiguous
            corrected["pitcher_attribution_method"] = (
                "explicit_play_text"
                if block["explicit"]
                else "boxscore_constrained_unique"
                if not ambiguous
                else "boxscore_constrained_tied"
            )
            changed_pas += int(
                event.get("is_plate_appearance")
                and canonical_person_key(event.get("pitcher", "")) != corrected["pitcher_key"]
            )
            output.append(corrected)
    return output, {
        "pitchers": names,
        "target_outs": list(targets),
        "optimal_paths": len(best_paths),
        "ambiguous_blocks": ambiguous_blocks,
        "changed_plate_appearances": changed_pas,
    }


def reconstruct_pitcher_attribution(
    events: list[dict[str, Any]], boxscore: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_game[event["canonical_id"]].append(event)
    pitchers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in boxscore:
        if row["role"] == "pitching":
            pitchers[(row["canonical_id"], row["team"])].append(row)

    corrected = []
    audit = []
    for canonical_id, game_events in sorted(by_game.items()):
        for team in sorted({event["fielding_team"] for event in game_events}):
            team_events = [event for event in game_events if event["fielding_team"] == team]
            rebuilt, detail = _reconstruct_team_pitchers(
                team_events, pitchers[(canonical_id, team)]
            )
            corrected.extend(rebuilt)
            audit.append({"canonical_id": canonical_id, "fielding_team": team, **detail})
    corrected.sort(key=lambda event: (event["canonical_id"], event["event_order"]))
    return corrected, audit


def _validate_pitcher_outs(
    events: list[dict[str, Any]], boxscore: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    observed: Counter[tuple[str, str]] = Counter()
    for event in events:
        observed[(event["canonical_id"], event["pitcher_key"])] += (
            event["outs_after"] - event["outs_before"]
        )
    failures = []
    for row in boxscore:
        if row["role"] != "pitching":
            continue
        key = (row["canonical_id"], canonical_person_key(row["player"]))
        expected = round(float(row["innings_decimal"]) * 3)
        if observed[key] != expected:
            failures.append(
                {"canonical_id": key[0], "pitcher_key": key[1], "expected": expected, "observed": observed[key]}
            )
    return failures


def _stat_fields(event_type: str, woba_weights: dict[str, Any]) -> dict[str, Any]:
    hit = int(event_type in HIT_EVENTS)
    total_bases = {"single": 1, "double": 2, "triple": 3, "home_run": 4}.get(event_type, 0)
    return {
        "PA_value": 1,
        "AB_value": int(event_type not in AB_EXCLUSIONS),
        "H_value": hit,
        "TB_value": total_bases,
        "BB_value": int(event_type in WALK_EVENTS),
        "HBP_value": int(event_type == "hit_by_pitch"),
        "SF_value": int(event_type == "sacrifice_fly"),
        "SO_value": int(event_type in STRIKEOUT_EVENTS),
        "HR_value": int(event_type == "home_run"),
        "OBP_num_value": _obp_numerator(event_type),
        "OBP_den_value": int(event_type not in {"sacrifice_bunt", "catcher_interference"}),
        "wOBA_num_value": woba_weights["scaled_weights"].get(event_type, 0.0),
        "wOBA_den_value": _batting_denominator(event_type),
    }


def derive_exposures(
    events: list[dict[str, Any]],
    valued_events: list[dict[str, Any]],
    linear_weights: dict[str, float],
    canonical_games: list[dict[str, Any]],
    official_matches: dict[str, dict[str, Any]],
    series: dict[str, dict[str, Any]],
    woba_weights: dict[str, Any],
) -> list[dict[str, Any]]:
    values = {
        (event["canonical_id"], event["event_order"]): event.get("run_value")
        for event in valued_events
    }
    game_meta = {game["canonical_id"]: game for game in canonical_games}
    plate_appearances = [dict(event) for event in events if event["is_plate_appearance"]]
    plate_appearances.sort(
        key=lambda event: (
            _iso(official_matches[event["canonical_id"]]["gameDateIso"]),
            event["canonical_id"],
            event["event_order"],
        )
    )
    game_matchups: Counter[tuple[str, str, str]] = Counter()
    pitcher_bf: Counter[tuple[str, str]] = Counter()
    series_matchups: Counter[tuple[str, str, str]] = Counter()
    prior_series_games: Counter[tuple[str, str, str]] = Counter()
    output = []
    for canonical_id, game_group in groupby(plate_appearances, key=lambda event: event["canonical_id"]):
        game_rows = list(game_group)
        series_id = series[canonical_id]["series_id"]
        pending: Counter[tuple[str, str, str]] = Counter()
        for event in game_rows:
            batter_key = canonical_person_key(event["batter"])
            pitcher_key = event["pitcher_key"]
            game_key = (canonical_id, batter_key, pitcher_key)
            pitcher_key_game = (canonical_id, pitcher_key)
            series_key = (series_id, batter_key, pitcher_key)
            game_matchups[game_key] += 1
            series_matchups[series_key] += 1
            row = dict(event)
            row.update(
                {
                    "game_start": game_meta[canonical_id]["start_ts"],
                    "official_game_id": official_matches[canonical_id]["gameId"],
                    **series[canonical_id],
                    "batter_key": batter_key,
                    "same_game_matchup_number": game_matchups[game_key],
                    "pitcher_batters_faced_before": pitcher_bf[pitcher_key_game],
                    "mlb_tto_bf9": pitcher_bf[pitcher_key_game] // 9 + 1,
                    "series_matchup_number": series_matchups[series_key],
                    "prior_series_game_matchups": prior_series_games[series_key],
                    "re24_run_value": values.get((canonical_id, event["event_order"])),
                    "run_value": linear_weights[event["event_type"]],
                    **_stat_fields(event["event_type"], woba_weights),
                }
            )
            pitcher_bf[pitcher_key_game] += 1
            pending[series_key] += 1
            output.append(row)
        prior_series_games.update(pending)
    return output


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _cluster_ratio_ci(
    rows: list[dict[str, Any]], numerator: str, denominator: str
) -> tuple[float | None, float | None]:
    num = sum(float(row[numerator]) for row in rows)
    den = sum(float(row[denominator]) for row in rows)
    if not den:
        return None, None
    estimate = num / den
    clusters: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        clusters[row["canonical_id"]].append(row)
    if len(clusters) < 2:
        return None, None
    influences = [
        sum(float(row[numerator]) - estimate * float(row[denominator]) for row in group)
        for group in clusters.values()
    ]
    variance = len(clusters) / (len(clusters) - 1) * sum(value * value for value in influences) / (den * den)
    se = math.sqrt(max(0.0, variance))
    return estimate - 1.96 * se, estimate + 1.96 * se


def aggregate_rows(rows: list[dict[str, Any]], labels: dict[str, Any]) -> dict[str, Any]:
    totals = {field: sum(float(row[field]) for row in rows) for field in (
        "PA_value", "AB_value", "H_value", "TB_value", "BB_value", "HBP_value", "SF_value",
        "SO_value", "HR_value", "OBP_num_value", "OBP_den_value", "wOBA_num_value",
        "wOBA_den_value", "run_value",
    )}
    woba_low, woba_high = _cluster_ratio_ci(rows, "wOBA_num_value", "wOBA_den_value")
    rv_low, rv_high = _cluster_ratio_ci(rows, "run_value", "PA_value")
    return {
        **labels,
        "PA": len(rows),
        "games": len({row["canonical_id"] for row in rows}),
        "AB": int(totals["AB_value"]),
        "H": int(totals["H_value"]),
        "BB": int(totals["BB_value"]),
        "HBP": int(totals["HBP_value"]),
        "SO": int(totals["SO_value"]),
        "HR": int(totals["HR_value"]),
        "AVG": _ratio(totals["H_value"], totals["AB_value"]),
        "OBP": _ratio(totals["OBP_num_value"], totals["OBP_den_value"]),
        "SLG": _ratio(totals["TB_value"], totals["AB_value"]),
        "OPS": (
            (_ratio(totals["OBP_num_value"], totals["OBP_den_value"]) or 0.0)
            + (_ratio(totals["TB_value"], totals["AB_value"]) or 0.0)
        ),
        "K_pct": _ratio(totals["SO_value"], len(rows)),
        "BB_pct": _ratio(totals["BB_value"], len(rows)),
        "HR_pct": _ratio(totals["HR_value"], len(rows)),
        "wOBA": _ratio(totals["wOBA_num_value"], totals["wOBA_den_value"]),
        "wOBA_95_low": woba_low,
        "wOBA_95_high": woba_high,
        "RV_per_PA": _ratio(totals["run_value"], len(rows)),
        "RV_per_PA_95_low": rv_low,
        "RV_per_PA_95_high": rv_high,
    }


def _group_table(
    rows: list[dict[str, Any]], key, label_name: str, sort_key=None
) -> list[dict[str, Any]]:
    groups: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[key(row)].append(row)
    items = groups.items()
    if sort_key:
        items = sorted(items, key=lambda item: sort_key(item[0]))
    return [aggregate_rows(group, {label_name: label}) for label, group in items]


def build_descriptive_tables(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    same_game = _group_table(
        rows,
        lambda row: str(row["same_game_matchup_number"]) if row["same_game_matchup_number"] < 4 else "4+",
        "encounter",
        lambda value: int(value.rstrip("+")),
    )
    mlb_tto = _group_table(
        rows,
        lambda row: str(row["mlb_tto_bf9"]) if row["mlb_tto_bf9"] < 4 else "4+",
        "tto_bf9",
        lambda value: int(value.rstrip("+")),
    )
    series_exposure = _group_table(
        rows,
        lambda row: str(row["series_matchup_number"]) if row["series_matchup_number"] < 5 else "5+",
        "series_encounter",
        lambda value: int(value.rstrip("+")),
    )
    prior_series = _group_table(
        rows,
        lambda row: "0" if row["prior_series_game_matchups"] == 0 else "1-2" if row["prior_series_game_matchups"] <= 2 else "3+",
        "prior_series_game_encounters",
        lambda value: {"0": 0, "1-2": 1, "3+": 3}[value],
    )
    inning = _group_table(
        rows,
        lambda row: "1-2" if row["inning"] <= 2 else "3-4" if row["inning"] <= 4 else "5+",
        "innings",
        lambda value: {"1-2": 1, "3-4": 3, "5+": 5}[value],
    )
    season_same_game = _group_table(
        rows,
        lambda row: f"{row['season']}-{row['same_game_matchup_number'] if row['same_game_matchup_number'] < 3 else '3+'}",
        "season_encounter",
        lambda value: (int(value.split("-")[0]), int(value.split("-")[1].rstrip("+"))),
    )
    return {
        "same_game_matchup": same_game,
        "mlb_tto_bf9": mlb_tto,
        "series_matchup": series_exposure,
        "prior_series_games": prior_series,
        "inning_bands": inning,
        "season_same_game": season_same_game,
    }


def build_pitcher_tables(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        encounter = str(row["same_game_matchup_number"]) if row["same_game_matchup_number"] < 3 else "3+"
        groups[(row["pitcher_key"], encounter)].append(row)
    splits = []
    for (pitcher_key, encounter), group in sorted(groups.items()):
        splits.append(
            aggregate_rows(
                group,
                {
                    "pitcher_key": pitcher_key,
                    "pitcher": PERSON_DISPLAY_NAMES.get(
                        pitcher_key, Counter(row["pitcher"] for row in group).most_common(1)[0][0]
                    ),
                    "teams": sorted(
                        {_team_key(row["fielding_team"]).title() for row in rows if row["pitcher_key"] == pitcher_key}
                    ),
                    "encounter": encounter,
                },
            )
        )
    by_pitcher: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for row in splits:
        by_pitcher[row["pitcher_key"]][row["encounter"]] = row
    summary = []
    for pitcher_key, values in sorted(by_pitcher.items()):
        first = values.get("1")
        later = [row for label, row in values.items() if label != "1"]
        all_pitcher_rows = [row for row in rows if row["pitcher_key"] == pitcher_key]
        if not first:
            continue
        later_pas = sum(row["PA"] for row in later)
        later_aggregate = aggregate_rows(
            [row for row in all_pitcher_rows if row["same_game_matchup_number"] >= 2], {}
        ) if later_pas else None
        summary.append(
            {
                "pitcher_key": pitcher_key,
                "pitcher": first["pitcher"],
                "teams": first["teams"],
                "PA": len(all_pitcher_rows),
                "first_PA": first["PA"],
                "later_PA": later_pas,
                "first_OPS": first["OPS"],
                "later_OPS": later_aggregate["OPS"] if later_aggregate else None,
                "OPS_penalty": later_aggregate["OPS"] - first["OPS"] if later_aggregate else None,
                "first_wOBA": first["wOBA"],
                "first_wOBA_95_low": first["wOBA_95_low"],
                "first_wOBA_95_high": first["wOBA_95_high"],
                "later_wOBA": later_aggregate["wOBA"] if later_aggregate else None,
                "later_wOBA_95_low": later_aggregate["wOBA_95_low"] if later_aggregate else None,
                "later_wOBA_95_high": later_aggregate["wOBA_95_high"] if later_aggregate else None,
                "wOBA_penalty": later_aggregate["wOBA"] - first["wOBA"] if later_aggregate else None,
                "first_RV_per_PA": first["RV_per_PA"],
                "later_RV_per_PA": later_aggregate["RV_per_PA"] if later_aggregate else None,
                "RV_per_PA_penalty": later_aggregate["RV_per_PA"] - first["RV_per_PA"] if later_aggregate else None,
                "quality_flag": "small_later_sample" if later_pas < 30 else "",
            }
        )
    return splits, summary


def validate_tto_dataset(
    rows: list[dict[str, Any]], schedules: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    completed_official_ids = {
        int(game["gameId"])
        for schedule in schedules.values()
        for game in schedule["games"]
        if game.get("recordStatus") == "Completed"
        and game.get("seasonId") in OFFICIAL_SEASON_IDS.values()
    }
    output_official_ids = {int(row["official_game_id"]) for row in rows}

    def consecutive(values: Iterable[int], start: int) -> bool:
        ordered = sorted(values)
        return ordered == list(range(start, start + len(ordered)))

    game_matchups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    series_matchups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    pitcher_bf: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in rows:
        game_matchups[(row["canonical_id"], row["batter_key"], row["pitcher_key"])].append(
            int(row["same_game_matchup_number"])
        )
        series_matchups[(row["series_id"], row["batter_key"], row["pitcher_key"])].append(
            int(row["series_matchup_number"])
        )
        pitcher_bf[(row["canonical_id"], row["pitcher_key"])].append(
            int(row["pitcher_batters_faced_before"])
        )
    checks = [
        {
            "check": "every completed official game is represented",
            "passed": output_official_ids == completed_official_ids,
            "observed": len(output_official_ids),
            "expected": len(completed_official_ids),
        },
        {
            "check": "every PA has batter and pitcher identity",
            "passed": all(row.get("batter_key") and row.get("pitcher_key") for row in rows),
            "observed": sum(bool(row.get("batter_key") and row.get("pitcher_key")) for row in rows),
            "expected": len(rows),
        },
        {
            "check": "same-game matchup ordinals are consecutive",
            "passed": all(consecutive(values, 1) for values in game_matchups.values()),
            "observed": sum(consecutive(values, 1) for values in game_matchups.values()),
            "expected": len(game_matchups),
        },
        {
            "check": "series matchup ordinals are consecutive",
            "passed": all(consecutive(values, 1) for values in series_matchups.values()),
            "observed": sum(consecutive(values, 1) for values in series_matchups.values()),
            "expected": len(series_matchups),
        },
        {
            "check": "pitcher batters-faced counters are consecutive",
            "passed": all(consecutive(values, 0) for values in pitcher_bf.values()),
            "observed": sum(consecutive(values, 0) for values in pitcher_bf.values()),
            "expected": len(pitcher_bf),
        },
    ]
    result = {"passed": all(check["passed"] for check in checks), "checks": checks}
    if not result["passed"]:
        raise ValueError(f"TTO dataset validation failed: {[row for row in checks if not row['passed']]}")
    return result


def _fit_fixed_effect_model(
    rows: list[dict[str, Any]], outcome: str, *, include_workload: bool
) -> dict[str, Any]:
    model_rows = [row for row in rows if outcome != "wOBA_value" or row["wOBA_den_value"]]
    batters = sorted({row["batter_key"] for row in model_rows})
    pitchers = sorted({row["pitcher_key"] for row in model_rows})
    named_columns = [
        "intercept",
        "same_game_encounter_2",
        "same_game_encounter_3plus",
        "prior_series_games_1_2",
        "prior_series_games_3plus",
        "season_2026",
    ]
    if include_workload:
        named_columns[5:5] = [
            "pitcher_bf_before_per_9",
            "inning_3_4",
            "inning_5plus",
        ]
    columns = named_columns + [f"batter:{key}" for key in batters[1:]] + [f"pitcher:{key}" for key in pitchers[1:]]
    batter_index = {key: index for index, key in enumerate(batters[1:], len(named_columns))}
    pitcher_index = {key: index for index, key in enumerate(pitchers[1:], len(named_columns) + len(batters) - 1)}
    x = np.zeros((len(model_rows), len(columns)), dtype=float)
    y = np.zeros(len(model_rows), dtype=float)
    for index, row in enumerate(model_rows):
        base_values = [
            1.0,
            float(row["same_game_matchup_number"] == 2),
            float(row["same_game_matchup_number"] >= 3),
            float(1 <= row["prior_series_game_matchups"] <= 2),
            float(row["prior_series_game_matchups"] >= 3),
            float(row["season"] == 2026),
        ]
        if include_workload:
            base_values[5:5] = [
                row["pitcher_batters_faced_before"] / 9.0,
                float(3 <= row["inning"] <= 4),
                float(row["inning"] >= 5),
            ]
        x[index, : len(named_columns)] = base_values
        if row["batter_key"] in batter_index:
            x[index, batter_index[row["batter_key"]]] = 1.0
        if row["pitcher_key"] in pitcher_index:
            x[index, pitcher_index[row["pitcher_key"]]] = 1.0
        y[index] = (
            row["run_value"]
            if outcome == "run_value"
            else row["wOBA_num_value"]
            if outcome == "wOBA_value"
            else row["OBP_num_value"]
        )
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    residual = y - x @ beta
    bread = np.linalg.pinv(x.T @ x)
    meat = np.zeros((x.shape[1], x.shape[1]))
    clusters: dict[str, list[int]] = defaultdict(list)
    for index, row in enumerate(model_rows):
        clusters[row["canonical_id"]].append(index)
    for indices in clusters.values():
        score = x[indices].T @ residual[indices]
        meat += np.outer(score, score)
    covariance = bread @ meat @ bread
    if len(clusters) > 1:
        covariance *= len(clusters) / (len(clusters) - 1)
    standard_errors = np.sqrt(np.maximum(0.0, np.diag(covariance)))
    coefficients = []
    for index, name in enumerate(named_columns[1:], 1):
        coefficients.append(
            {
                "term": name,
                "estimate": float(beta[index]),
                "standard_error": float(standard_errors[index]),
                "ci_95_low": float(beta[index] - 1.96 * standard_errors[index]),
                "ci_95_high": float(beta[index] + 1.96 * standard_errors[index]),
            }
        )
    return {
        "outcome": outcome,
        "model_spec": "workload_decomposition" if include_workload else "total_exposure_association",
        "n": len(model_rows),
        "games": len(clusters),
        "batter_fixed_effects": len(batters),
        "pitcher_fixed_effects": len(pitchers),
        "design_columns": len(columns),
        "design_rank": int(np.linalg.matrix_rank(x)),
        "coefficients": coefficients,
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in row.items()
                }
            )


def _fmt(value: float | None, digits: int = 3) -> str:
    return "—" if value is None else f"{value:.{digits}f}"


def _report(
    snapshot_id: str,
    rows: list[dict[str, Any]],
    tables: dict[str, list[dict[str, Any]]],
    models: list[dict[str, Any]],
    attribution_audit: list[dict[str, Any]],
    schedule_audit: list[dict[str, Any]],
    pitcher_summary: list[dict[str, Any]],
    official_pbp_audit: list[dict[str, Any]],
) -> str:
    same = tables["same_game_matchup"]
    first = next(row for row in same if row["encounter"] == "1")
    later = aggregate_rows([row for row in rows if row["same_game_matchup_number"] >= 2], {})
    third = next((row for row in same if row["encounter"] == "3"), None)
    lines = [
        "# AUSL Times Through the Order and Repeated Exposure",
        "",
        f"Snapshot: `{snapshot_id}`",
        "",
        "## Executive result",
        "",
        (
            f"Across {len(rows):,} plate appearances in {len({row['canonical_id'] for row in rows})} games, "
            f"hitters produced a {_fmt(first['OPS'])} OPS and {_fmt(first['wOBA'])} wOBA the first time they "
            f"faced the same pitcher in a game. In all later meetings combined, those figures were "
            f"{_fmt(later['OPS'])} and {_fmt(later['wOBA'])}. The observed penalties were "
            f"{_fmt(later['OPS'] - first['OPS'])} OPS and {_fmt(later['wOBA'] - first['wOBA'])} wOBA."
        ),
        "",
    ]
    if third:
        lines.append(
            f"The third same-game meeting contained {third['PA']:,} PA and produced a {_fmt(third['OPS'])} OPS, "
            f"{_fmt(third['wOBA'])} wOBA, and {_fmt(third['RV_per_PA'])} context-neutral event runs per PA."
        )
        lines.append("")
    total_run_model = next(
        model for model in models
        if model["model_spec"] == "total_exposure_association" and model["outcome"] == "run_value"
    )
    workload_run_model = next(
        model for model in models
        if model["model_spec"] == "workload_decomposition" and model["outcome"] == "run_value"
    )
    coefficient = lambda model, term: next(
        row for row in model["coefficients"] if row["term"] == term
    )
    total_third = coefficient(total_run_model, "same_game_encounter_3plus")
    workload = coefficient(workload_run_model, "pitcher_bf_before_per_9")
    lines += [
        "These are league-level descriptive differences. Pitcher survival, score state, substitutions, and the "
        "quality of hitters who receive later opportunities create selection effects. The adjusted models below "
        "reduce some confounding but do not make the estimates causal.",
        "",
        (
            f"The adjusted total association remains positive for the third-or-later meeting: "
            f"{_fmt(total_third['estimate'])} context-neutral event runs per PA (95% CI "
            f"{_fmt(total_third['ci_95_low'])} to {_fmt(total_third['ci_95_high'])}). When pitcher workload is "
            f"modeled directly, each additional nine batters faced is associated with "
            f"{_fmt(workload['estimate'])} more context-neutral event runs per PA (95% CI {_fmt(workload['ci_95_low'])} to "
            f"{_fmt(workload['ci_95_high'])}). The exact encounter indicators are no longer positive in that "
            "decomposition. The evidence therefore supports deterioration as pitchers progress through a game, "
            "but does not isolate a separate familiarity jump at the instant a hitter sees the same pitcher again."
        ),
        "",
        "## Same pitcher, same game",
        "",
        "| Encounter | PA | AVG | OBP | SLG | OPS | K% | BB% | HR% | wOBA | RV/PA |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in same:
        lines.append(
            f"| {row['encounter']} | {row['PA']} | {_fmt(row['AVG'])} | {_fmt(row['OBP'])} | "
            f"{_fmt(row['SLG'])} | {_fmt(row['OPS'])} | {_fmt(row['K_pct'] * 100, 1)}% | "
            f"{_fmt(row['BB_pct'] * 100, 1)}% | {_fmt(row['HR_pct'] * 100, 1)}% | "
            f"{_fmt(row['wOBA'])} | {_fmt(row['RV_per_PA'])} |"
        )
    lines += [
        "",
        "## Season check",
        "",
        "| Season / encounter | PA | OPS | wOBA | RV/PA |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in tables["season_same_game"]:
        lines.append(
            f"| {row['season_encounter']} | {row['PA']} | {_fmt(row['OPS'])} | "
            f"{_fmt(row['wOBA'])} | {_fmt(row['RV_per_PA'])} |"
        )
    lines += [
        "",
        "The direction is present in both seasons from the first to the second encounter, but the third-or-later "
        "increase is much larger in 2025. The pooled estimate should therefore be treated as a two-season league "
        "average, not a fixed law that is equally large every year.",
        "",
    ]
    lines += [
        "",
        "## Exposure carried across an official series",
        "",
        "`Prior series-game encounters` counts only meetings with the same pitcher in earlier games of the current "
        "official series. It does not include earlier meetings in the same game.",
        "",
        "| Prior series-game encounters | PA | OPS | wOBA | RV/PA |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in tables["prior_series_games"]:
        lines.append(
            f"| {row['prior_series_game_encounters']} | {row['PA']} | {_fmt(row['OPS'])} | "
            f"{_fmt(row['wOBA'])} | {_fmt(row['RV_per_PA'])} |"
        )
    lines += [
        "",
        "The series pattern is not monotonic: the 1–2 prior-meeting group is higher than zero exposure, but the "
        "3+ group is lower and contains a much smaller sample. This snapshot does not establish a stable cumulative "
        "series penalty.",
        "",
        "## Offense by game stage",
        "",
        "| Innings | PA | OPS | wOBA | RV/PA |",
        "|---:|---:|---:|---:|---:|",
    ]
    for row in tables["inning_bands"]:
        lines.append(
            f"| {row['innings']} | {row['PA']} | {_fmt(row['OPS'])} | {_fmt(row['wOBA'])} | "
            f"{_fmt(row['RV_per_PA'])} |"
        )
    lines += [
        "",
        "League-wide offense is not highest in innings 5 and later. That does not contradict the pitcher-workload "
        "result: late innings also contain fresh relievers and selective pitcher removal, while pitchers who remain "
        "in the game show deterioration as their batters-faced count rises.",
        "",
    ]
    lines += [
        "",
        "## Adjusted associations",
        "",
        "The total-exposure models use batter and pitcher fixed effects, season, and prior-series exposure. The "
        "workload-decomposition models add pitcher batters faced and inning band. The latter asks whether an exact "
        "repeat meeting adds a discontinuous penalty beyond the pitcher's gradual progression through the game. "
        "Standard errors are clustered by game.",
        "",
        "| Model | Outcome | Term | Estimate | 95% CI |",
        "|---|---|---|---:|---:|",
    ]
    for model in models:
        for coefficient in model["coefficients"]:
            if coefficient["term"] in {"same_game_encounter_2", "same_game_encounter_3plus", "prior_series_games_1_2", "prior_series_games_3plus", "pitcher_bf_before_per_9", "inning_5plus"}:
                lines.append(
                    f"| {model['model_spec']} | {model['outcome']} | {coefficient['term']} | {_fmt(coefficient['estimate'])} | "
                    f"[{_fmt(coefficient['ci_95_low'])}, {_fmt(coefficient['ci_95_high'])}] |"
                )
    lines += [
        "",
        "## Individual pitcher penalties",
        "",
        "Positive values mean hitters performed better after their first same-game meeting. Small later samples "
        "are retained but flagged; they should not be treated as stable pitcher traits.",
        "",
        "| Pitcher | PA | Later PA | First OPS | Later OPS | OPS penalty | First wOBA | Later wOBA | wOBA penalty | Flag |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in sorted(pitcher_summary, key=lambda item: (-item["PA"], item["pitcher"])):
        lines.append(
            f"| {row['pitcher']} | {row['PA']} | {row['later_PA']} | {_fmt(row['first_OPS'])} | "
            f"{_fmt(row['later_OPS'])} | {_fmt(row['OPS_penalty'])} | {_fmt(row['first_wOBA'])} | "
            f"{_fmt(row['later_wOBA'])} | {_fmt(row['wOBA_penalty'])} | {row['quality_flag']} |"
        )
    changed = sum(row["changed_plate_appearances"] for row in attribution_audit)
    ambiguous = sum(row["ambiguous_blocks"] for row in attribution_audit)
    score_disagreements = sum(row["match_method"].endswith("score_disagreement") for row in schedule_audit)
    lines += [
        "",
        "## Data quality and interpretation",
        "",
        f"- Pitcher stint reconstruction changed {changed:,} PA assignments relative to the original carry-forward parser.",
        f"- All pitcher-game outs now reconcile exactly to the pitching box score. {ambiguous} event blocks remain tied between equally optimal assignments and are flagged in the PA data.",
        f"- {len(schedule_audit) - score_disagreements}/{len(schedule_audit)} games matched the official AUSL schedule by teams, date, and score; {score_disagreements} matched uniquely by teams and date despite a source score discrepancy.",
        f"- {len(official_pbp_audit)} additional completed games absent from the inherited GameChanger PA snapshot were added from official AUSL play-by-play. Every official PA has batter and pitcher IDs, and every game reconciles PA, H, BB, SO, and HR totals to its official box score.",
        "- The MLB-comparable field is a nine-batters-faced band (`mlb_tto_bf9`). The exact batter-pitcher encounter is the primary softball measure because re-entry and nonstandard lineup use can break a simple lineup-turn definition.",
        "- A scheduled series is defined from the official AUSL team pairing, venue, and date cluster; postseason series use the official postseason series identifier.",
        "- Together, the GameChanger-derived games and official AUSL augmentation cover every game marked completed in the captured 2025 and 2026 official schedules. Postponed and suspended duplicate/resumption records are excluded.",
        "- RV/PA is the context-neutral event value derived from the shared AUSL RE24 event weights, making it comparable across both source types. The original contextual RE24 value remains in `re24_run_value` where GameChanger base-out states are available.",
        "",
        "## Reproducibility",
        "",
        "```bash",
        f"PYTHONPATH=src python3 -m ausl_war.cli build-tto --snapshot {snapshot_id}",
        "PYTHONPATH=src python3 -m unittest discover -s tests -v",
        "```",
        "",
        "MLB comparison references:",
        "",
        "- https://www.mlb.com/glossary/miscellaneous/third-time-through-the-order-penalty",
        "- https://baseballsavant.mlb.com/csv-docs",
    ]
    return "\n".join(lines) + "\n"


def build_tto_study(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    events = read_json(snapshot / "normalized" / "events.json")
    boxscore = read_json(snapshot / "normalized" / "player_game_boxscore.json")
    valued_events = read_json(snapshot / "model" / "valued_events.json")
    linear_weights = {
        row["event_type"]: float(row["linear_weight"])
        for row in read_json(snapshot / "model" / "event_linear_weights.json")
    }
    canonical_games = read_json(snapshot / "public" / "canonical_games.json")
    schedules = _download_official_schedules(project_root, snapshot_id)
    official_matches, schedule_audit = match_official_games(canonical_games, schedules)
    matched_official_ids = {int(game["gameId"]) for game in official_matches.values()}
    unmatched_official = [
        game
        for schedule in schedules.values()
        for game in schedule["games"]
        if game.get("recordStatus") == "Completed"
        and int(game["gameId"]) not in matched_official_ids
        and game.get("seasonId") in OFFICIAL_SEASON_IDS.values()
    ]
    official_pages = _download_official_game_pages(project_root, snapshot_id, unmatched_official)
    official_events = []
    official_pbp_audit = []
    augmented_games = list(canonical_games)
    all_official_matches = dict(official_matches)
    for game in unmatched_official:
        season = 2025 if game["seasonId"] == OFFICIAL_SEASON_IDS[2025] else 2026
        canonical_id = f"official-ausl-{season}-{game['gameId']}"
        parsed, audit = parse_official_game_pas(
            game, official_pages[int(game["gameId"])], canonical_id
        )
        official_events.extend(parsed)
        official_pbp_audit.append(audit)
        all_official_matches[canonical_id] = game
        augmented_games.append(
            {
                "canonical_id": canonical_id,
                "season": season,
                "start_ts": game["gameDateIso"],
                "status": "completed",
                "team_names": [row["name"] for row in game.get("competitors", [])],
            }
        )
    series = assign_series_ids(all_official_matches)
    corrected_events, attribution_audit = reconstruct_pitcher_attribution(events, boxscore)
    pitcher_out_failures = _validate_pitcher_outs(corrected_events, boxscore)
    if pitcher_out_failures:
        raise ValueError(f"Pitcher attribution does not reconcile: {pitcher_out_failures[:5]}")
    woba_weights = derive_woba_constants(valued_events)
    for event in corrected_events:
        event.setdefault("source_kind", "gamechanger_normalized")
    pa_rows = derive_exposures(
        corrected_events + official_events,
        valued_events,
        linear_weights,
        augmented_games,
        all_official_matches,
        series,
        woba_weights,
    )
    validation = validate_tto_dataset(pa_rows, schedules)
    tables = build_descriptive_tables(pa_rows)
    pitcher_splits, pitcher_summary = build_pitcher_tables(pa_rows)
    models = [
        _fit_fixed_effect_model(pa_rows, outcome, include_workload=include_workload)
        for include_workload in (False, True)
        for outcome in ("run_value", "wOBA_value", "on_base")
    ]
    output = project_root / "output" / "tto"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "plate_appearances.json", pa_rows)
    _write_csv(output / "plate_appearances.csv", pa_rows)
    write_json(output / "league_splits.json", tables)
    for name, rows in tables.items():
        _write_csv(output / f"league_{name}.csv", rows)
    write_json(output / "pitcher_splits.json", pitcher_splits)
    _write_csv(output / "pitcher_splits.csv", pitcher_splits)
    write_json(output / "pitcher_penalties.json", pitcher_summary)
    _write_csv(output / "pitcher_penalties.csv", pitcher_summary)
    write_json(output / "adjusted_models.json", models)
    write_json(output / "pitcher_attribution_audit.json", attribution_audit)
    _write_csv(output / "pitcher_attribution_audit.csv", attribution_audit)
    write_json(output / "official_schedule_match_audit.json", schedule_audit)
    _write_csv(output / "official_schedule_match_audit.csv", schedule_audit)
    write_json(output / "official_pbp_audit.json", official_pbp_audit)
    _write_csv(output / "official_pbp_audit.csv", official_pbp_audit)
    write_json(output / "validation.json", validation)
    (output / "Report.md").write_text(
        _report(
            snapshot_id,
            pa_rows,
            tables,
            models,
            attribution_audit,
            schedule_audit,
            pitcher_summary,
            official_pbp_audit,
        ),
        encoding="utf-8",
    )
    summary = {
        "snapshot_id": snapshot_id,
        "games": len({row["canonical_id"] for row in pa_rows}),
        "plate_appearances": len(pa_rows),
        "pitchers": len({row["pitcher_key"] for row in pa_rows}),
        "series": len({row["series_id"] for row in pa_rows}),
        "pitcher_game_rows": len(attribution_audit),
        "pitcher_out_reconciliation_failures": len(pitcher_out_failures),
        "changed_pitcher_plate_appearances": sum(row["changed_plate_appearances"] for row in attribution_audit),
        "ambiguous_attribution_blocks": sum(row["ambiguous_blocks"] for row in attribution_audit),
        "gamechanger_schedule_matches": len(schedule_audit),
        "official_augmented_games": len(official_pbp_audit),
        "official_pbp_validation_failures": sum(
            row["plate_appearances"] != row["boxscore_batters_faced"] or row["unknown_outcomes"]
            for row in official_pbp_audit
        ),
        "dataset_validation_passed": validation["passed"],
        "output": str(output),
    }
    write_json(output / "summary.json", summary)
    return summary
