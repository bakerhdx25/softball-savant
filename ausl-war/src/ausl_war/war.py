from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .io import read_json, write_json
from .normalize import normalize_person_name
from .official import (
    completed_schedule,
    canonical_person_key,
    display_team,
    official_stats,
    supplemental_boxscore_rows,
    supplemental_normalized_events,
    team_run_totals,
)


WOBA_EVENTS = {"single", "double", "triple", "home_run", "walk", "hit_by_pitch"}
OUT_EVENTS = {
    "out",
    "strikeout",
    "double_play",
    "fielders_choice",
    "infield_fly",
    "batter_interference",
    "dropped_third_out",
}
ON_BASE_EVENTS = {
    "single",
    "double",
    "triple",
    "home_run",
    "walk",
    "intentional_walk",
    "hit_by_pitch",
    "reached_on_error",
    "fielders_choice",
    "dropped_third_reached",
}
FIELDING_POSITIONS = (
    "first baseman",
    "second baseman",
    "third baseman",
    "center fielder",
    "right fielder",
    "left fielder",
    "shortstop",
    "pitcher",
    "catcher",
)


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _canonicalize_component_map(rows: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for source in rows.values():
        key = canonical_person_key(source.get("player") or source.get("player_key") or "")
        if key not in output:
            output[key] = dict(source)
            output[key]["player_key"] = key
            continue
        target = output[key]
        for field, value in source.items():
            if field in {"player", "player_key", "coverage"}:
                continue
            if isinstance(value, (int, float)) and isinstance(target.get(field, 0), (int, float)):
                target[field] = target.get(field, 0) + value
            elif isinstance(value, list):
                target[field] = sorted(set(target.get(field, [])) | set(value))
            elif isinstance(value, set):
                target[field] = set(target.get(field, set())) | value
            elif field not in target:
                target[field] = value
    return output


def _weighted_mean(rows: Iterable[dict[str, Any]], value: str, weight: str) -> float:
    rows = list(rows)
    denominator = sum(float(row[weight]) for row in rows)
    return sum(float(row[value]) * float(row[weight]) for row in rows) / denominator


def _batting_denominator(event_type: str) -> int:
    return int(event_type not in {"intentional_walk", "sacrifice_bunt", "catcher_interference"})


def _obp_numerator(event_type: str) -> int:
    return int(event_type in {"single", "double", "triple", "home_run", "walk", "intentional_walk", "hit_by_pitch"})


def _fielding_target(text: str, known_names: list[str]) -> tuple[str, str] | None:
    low = text.lower()
    candidates: list[tuple[int, str]] = []
    for position in FIELDING_POSITIONS:
        index = low.find(position)
        if index >= 0:
            candidates.append((index, position))
    if not candidates:
        return None
    index, position = min(candidates)
    tail = low[index + len(position):]
    named = [
        (tail.find(name.lower()), name)
        for name in known_names
        if tail.find(name.lower()) >= 0
    ]
    return (position, min(named)[1]) if named else None


def _primary_fielding_position(text: str) -> str | None:
    low = text.lower()
    candidates = [(low.find(position), position) for position in FIELDING_POSITIONS if position in low]
    return min(candidates)[1] if candidates else None


def _batted_ball_type(text: str) -> str | None:
    low = text.lower()
    for label, patterns in (
        ("bunt", ("bunt",)),
        ("ground", ("ground ball", "grounds ", "grounded ", "grounded out", "bunt")),
        ("line", ("line drive", "lines ", "lined ")),
        ("pop", ("pop fly", "pops ", "popped ", "infield fly")),
        ("fly", ("fly ball", "flies ", "flied ")),
    ):
        if any(pattern in low for pattern in patterns):
            return label
    return None


def derive_woba_constants(
    valued_events: list[dict[str, Any]],
    target_events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    plate_appearances = [event for event in valued_events if event.get("is_plate_appearance")]
    out_values = [event["run_value"] for event in plate_appearances if event["event_type"] in OUT_EVENTS]
    out_value = sum(out_values) / len(out_values)
    raw_weights = {}
    for event_type in WOBA_EVENTS:
        values = [
            float(event["run_value"])
            for event in plate_appearances
            if event["event_type"] == event_type
        ]
        raw_weights[event_type] = sum(values) / len(values) - out_value

    target_plate_appearances = [
        event for event in (target_events or valued_events) if event.get("is_plate_appearance")
    ]
    denominator = sum(
        _batting_denominator(event["event_type"]) for event in target_plate_appearances
    )
    obp_numerator = sum(
        _obp_numerator(event["event_type"]) for event in target_plate_appearances
    )
    unscaled_numerator = sum(
        raw_weights.get(event["event_type"], 0.0) for event in target_plate_appearances
    )
    league_obp = obp_numerator / denominator
    unscaled_woba = unscaled_numerator / denominator
    scale = league_obp / unscaled_woba
    return {
        "out_run_value": out_value,
        "raw_weights": raw_weights,
        "scaled_weights": {key: value * scale for key, value in raw_weights.items()},
        "woba_scale": scale,
        "league_woba": league_obp,
        "league_obp": league_obp,
        "calibration_pa": denominator,
    }


def aggregate_offense(
    events: list[dict[str, Any]],
    constants: dict[str, Any],
    group_by_team: bool = False,
) -> list[dict[str, Any]]:
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    raw_weights = constants["raw_weights"]
    for event in events:
        if not event.get("is_plate_appearance") or not event.get("batter"):
            continue
        player = event["batter"]
        key_parts = [event.get("batter_key") or canonical_person_key(player)]
        if group_by_team:
            key_parts.append(event["batting_team"])
        key = tuple(key_parts)
        row = groups.setdefault(
            key,
            {
                "player_key": key[0],
                "player": player,
                "teams": set(),
                "PA": 0,
                "woba_denom": 0,
                "obp_numerator": 0,
                "woba_raw_numerator": 0.0,
                "H": 0,
                "1B": 0,
                "2B": 0,
                "3B": 0,
                "HR": 0,
                "BB": 0,
                "IBB": 0,
                "HBP": 0,
                "SO": 0,
                "ROE": 0,
                "SF": 0,
                "SH": 0,
                "reach_opportunities": 0,
            },
        )
        event_type = event["event_type"]
        row["teams"].add(event["batting_team"])
        row["PA"] += 1
        row["woba_denom"] += _batting_denominator(event_type)
        row["obp_numerator"] += _obp_numerator(event_type)
        row["woba_raw_numerator"] += raw_weights.get(event_type, 0.0)
        row["reach_opportunities"] += int(event_type in ON_BASE_EVENTS)
        if event_type in {"single", "double", "triple", "home_run"}:
            row["H"] += 1
            row[{"single": "1B", "double": "2B", "triple": "3B", "home_run": "HR"}[event_type]] += 1
        elif event_type == "walk":
            row["BB"] += 1
        elif event_type == "intentional_walk":
            row["BB"] += 1
            row["IBB"] += 1
        elif event_type == "hit_by_pitch":
            row["HBP"] += 1
        elif event_type in {"strikeout", "dropped_third_out", "dropped_third_reached"}:
            row["SO"] += 1
        elif event_type == "reached_on_error":
            row["ROE"] += 1
        elif event_type == "sacrifice_fly":
            row["SF"] += 1
        elif event_type == "sacrifice_bunt":
            row["SH"] += 1

    output = []
    for row in groups.values():
        denom = row["woba_denom"]
        unscaled = row["woba_raw_numerator"] / denom if denom else 0.0
        row["wOBA"] = unscaled * constants["woba_scale"]
        row["OBP"] = row["obp_numerator"] / denom if denom else 0.0
        row["batting_runs"] = (
            (row["wOBA"] - constants["league_woba"])
            / constants["woba_scale"]
            * denom
        )
        row["teams"] = sorted(row["teams"])
        if group_by_team:
            row["team"] = row["teams"][0]
        output.append(row)
    return output


def _empty_offense_row(player_key: str, player: str, teams: list[str]) -> dict[str, Any]:
    return {
        "player_key": player_key,
        "player": player,
        "teams": sorted(set(teams)),
        "PA": 0,
        "woba_denom": 0,
        "obp_numerator": 0,
        "woba_raw_numerator": 0.0,
        "H": 0,
        "1B": 0,
        "2B": 0,
        "3B": 0,
        "HR": 0,
        "BB": 0,
        "IBB": 0,
        "HBP": 0,
        "SO": 0,
        "ROE": 0,
        "SF": 0,
        "SH": 0,
        "reach_opportunities": 0,
        "wOBA": 0.0,
        "OBP": 0.0,
        "batting_runs": 0.0,
    }


def baserunning_runs(
    events: list[dict[str, Any]],
    offense: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    raw_runs: dict[str, float] = defaultdict(float)
    attempts: Counter[str] = Counter()
    names: dict[str, str] = {}
    for event in events:
        if event["event_type"] not in {"stolen_base", "caught_stealing"}:
            continue
        actions = event.get("runner_actions") or []
        primary = next(
            (action for action in actions if action.get("action") in {"advance", "out"}),
            None,
        )
        if not primary:
            continue
        player = primary["runner"]
        key = normalize_person_name(player)
        names[key] = player
        raw_runs[key] += float(event["run_value"])
        attempts[key] += 1

    offense_by_key = {row["player_key"]: row for row in offense}
    all_keys = set(offense_by_key) | set(raw_runs)
    opportunities = {
        key: max(offense_by_key.get(key, {}).get("reach_opportunities", 0), attempts[key])
        for key in all_keys
    }
    total_opportunities = sum(opportunities.values())
    league_rate = sum(raw_runs.values()) / total_opportunities if total_opportunities else 0.0
    return {
        key: {
            "player": offense_by_key.get(key, {}).get("player") or names.get(key, key),
            "sb_cs_attempts": attempts[key],
            "baserunning_opportunities": opportunities[key],
            "sb_cs_raw_runs": raw_runs[key],
            "baserunning_runs": raw_runs[key] - opportunities[key] * league_rate,
            "coverage": "SB/CS only; non-steal advancement excluded",
        }
        for key in all_keys
    }


def _runner_map(event: dict[str, Any], field: str) -> dict[int, str]:
    return {int(base): runner for base, runner in (event.get(field) or {}).items()}


def _runner_base(runners: dict[int, str], player: str) -> int | None:
    key = normalize_person_name(player)
    return next(
        (base for base, runner in runners.items() if normalize_person_name(runner) == key),
        None,
    )


def _re_value(expectancy: dict[tuple[int, int], float], outs: int, bases: int) -> float:
    return 0.0 if outs >= 3 else expectancy[(outs, bases)]


def value_supplemental_events(
    events: list[dict[str, Any]], re24_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    expectancy = {
        (int(row["outs"]), int(row["bases"])): float(row["smoothed_re"])
        for row in re24_rows
    }
    output = []
    for source in events:
        event = dict(source)
        event["run_value"] = (
            float(event.get("runs_scored", 0))
            + _re_value(expectancy, int(event["outs_after"]), int(event["bases_after"]))
            - _re_value(expectancy, int(event["outs_before"]), int(event["bases_before"]))
        )
        output.append(event)
    return output


def _unambiguous_arm_target(
    event: dict[str, Any], known_players: list[str]
) -> tuple[str, str] | None:
    text = event.get("play_text") or ""
    low = text.lower()
    position_mentions = sum(low.count(position) for position in FIELDING_POSITIONS)
    if position_mentions != 1:
        return None
    return _fielding_target(text, known_players)


def expanded_baserunning_runs(
    events: list[dict[str, Any]],
    offense: list[dict[str, Any]],
    re24_rows: list[dict[str, Any]],
    known_players: list[str],
    prior_opportunities: float = 10.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    """Value non-forced runner and batter advancement relative to comparable plays."""
    expectancy = {
        (int(row["outs"]), int(row["bases"])): float(row["smoothed_re"])
        for row in re24_rows
    }
    eligible_runner_events = {
        "single", "double", "out", "sacrifice_fly", "infield_fly", "reached_on_error"
    }
    batter_events = {"single", "double", "reached_on_error"}
    opportunities: list[dict[str, Any]] = []
    unresolved_rows: list[dict[str, Any]] = []

    for event in events:
        if not event.get("is_plate_appearance"):
            continue
        event_type = event["event_type"]
        if event_type not in eligible_runner_events | batter_events:
            continue
        before = _runner_map(event, "runners_before")
        after = _runner_map(event, "runners_after")
        actions = event.get("runner_actions") or []
        batted_type = _batted_ball_type(event.get("play_text") or "") or "unknown"
        target = _unambiguous_arm_target(event, known_players)
        position = target[0] if target else "unattributed"
        fielder = target[1] if target else None

        candidates: list[tuple[str, int, str, int | None, str]] = []
        if event_type in eligible_runner_events:
            for start_base, runner in before.items():
                if runner == "__placed_runner__":
                    continue
                action = next(
                    (
                        item for item in actions
                        if normalize_person_name(item.get("runner", ""))
                        == normalize_person_name(runner)
                    ),
                    None,
                )
                if action:
                    if action["action"] in {"forced", "state_correction"}:
                        continue
                    candidates.append(
                        (runner, start_base, action["action"], action.get("to_base"), "runner")
                    )
                    continue
                end_base = _runner_base(after, runner)
                if end_base is not None:
                    candidates.append(
                        (runner, start_base, "remain" if end_base == start_base else "advance", end_base, "runner")
                    )
                else:
                    unresolved_rows.append(
                        {
                            "canonical_id": event.get("canonical_id"),
                            "event_order": event.get("event_order"),
                            "player": runner,
                            "reason": "incumbent runner absent after play without explicit action",
                            "play_text": event.get("play_text"),
                        }
                    )

        batter = event.get("batter")
        if event_type in batter_events and batter:
            explicit = next(
                (
                    item for item in actions
                    if normalize_person_name(item.get("runner", ""))
                    == normalize_person_name(batter)
                ),
                None,
            )
            if explicit:
                candidates.append(
                    (batter, 0, explicit["action"], explicit.get("to_base"), "batter")
                )
            else:
                end_base = _runner_base(after, batter)
                if end_base is not None:
                    candidates.append((batter, 0, "advance", end_base, "batter"))
                else:
                    unresolved_rows.append(
                        {
                            "canonical_id": event.get("canonical_id"),
                            "event_order": event.get("event_order"),
                            "player": batter,
                            "reason": "batter absent after advancement-eligible play without explicit action",
                            "play_text": event.get("play_text"),
                        }
                    )

        for player, start_base, action, destination, role in candidates:
            actual_out = int(action == "out")
            other_outs = max(int(event["outs_before"]), int(event["outs_after"]) - actual_out)
            bases_without = int(event["bases_after"])
            actual_base = _runner_base(after, player)
            if actual_base:
                bases_without &= ~(1 << (actual_base - 1))
            if action == "score":
                utility = 1.0 + _re_value(expectancy, other_outs, bases_without)
            elif action == "out":
                utility = _re_value(expectancy, other_outs + 1, bases_without)
            elif destination in (1, 2, 3):
                utility = _re_value(
                    expectancy, other_outs, bases_without | (1 << (int(destination) - 1))
                )
            else:
                unresolved_rows.append(
                    {
                        "canonical_id": event.get("canonical_id"),
                        "event_order": event.get("event_order"),
                        "player": player,
                        "reason": "eligible action has no valid destination",
                        "play_text": event.get("play_text"),
                    }
                )
                continue
            broad_group = (role, start_base, int(event["outs_before"]), event_type)
            detailed_group = broad_group + (batted_type, position)
            opportunities.append(
                {
                    "player": player,
                    "player_key": normalize_person_name(player),
                    "role": role,
                    "start_base": start_base,
                    "action": action,
                    "destination": destination,
                    "event_type": event_type,
                    "batted_type": batted_type,
                    "fielding_position": position,
                    "fielder": fielder,
                    "batting_team": event.get("batting_team"),
                    "fielding_team": event.get("fielding_team"),
                    "broad_group": broad_group,
                    "detailed_group": detailed_group,
                    "utility": utility,
                }
            )

    broad_values: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    detailed_values: dict[tuple[Any, ...], list[float]] = defaultdict(list)
    for row in opportunities:
        broad_values[row["broad_group"]].append(row["utility"])
        detailed_values[row["detailed_group"]].append(row["utility"])
    for row in opportunities:
        broad = broad_values[row["broad_group"]]
        detailed = detailed_values[row["detailed_group"]]
        broad_mean = sum(broad) / len(broad)
        expected = (sum(detailed) + prior_opportunities * broad_mean) / (
            len(detailed) + prior_opportunities
        )
        row["expected_utility"] = expected
        row["raw_value"] = row["utility"] - expected
    center = (
        sum(row["raw_value"] for row in opportunities) / len(opportunities)
        if opportunities else 0.0
    )
    for row in opportunities:
        row["advancement_runs"] = row["raw_value"] - center

    steal_rows = baserunning_runs(events, offense)
    offense_by_key = {row["player_key"]: row for row in offense}
    advancement_by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in opportunities:
        advancement_by_key[row["player_key"]].append(row)
    all_keys = set(offense_by_key) | set(steal_rows) | set(advancement_by_key)
    players: dict[str, dict[str, Any]] = {}
    for key in all_keys:
        rows = advancement_by_key[key]
        sb = steal_rows.get(key, {})
        advancement = sum(row["advancement_runs"] for row in rows)
        batter_advancement = sum(
            row["advancement_runs"] for row in rows if row["role"] == "batter"
        )
        sb_runs = float(sb.get("baserunning_runs", 0.0))
        players[key] = {
            "player": offense_by_key.get(key, {}).get("player") or sb.get("player") or (rows[0]["player"] if rows else key),
            "sb_cs_attempts": int(sb.get("sb_cs_attempts", 0)),
            "sb_cs_runs": sb_runs,
            "advancement_opportunities": len(rows),
            "runner_advancement_opportunities": sum(row["role"] == "runner" for row in rows),
            "batter_advancement_opportunities": sum(row["role"] == "batter" for row in rows),
            "non_steal_advancement_runs": advancement,
            "batter_advancement_runs": batter_advancement,
            "runner_advancement_runs": advancement - batter_advancement,
            "baserunning_runs": sb_runs + advancement,
            "teams": sorted(
                {
                    row["batting_team"]
                    for row in rows
                    if row.get("batting_team")
                }
            ),
            "coverage": "SB/CS plus non-forced hit/out advancement; WP/PB and forced advances excluded",
        }
    audit = {
        "advancement_opportunities": len(opportunities),
        "runner_opportunities": sum(row["role"] == "runner" for row in opportunities),
        "batter_opportunities": sum(row["role"] == "batter" for row in opportunities),
        "unresolved_candidate_transitions": len(unresolved_rows),
        "unresolved_transitions": unresolved_rows,
        "league_non_steal_advancement_runs": sum(
            row["advancement_runs"] for row in opportunities
        ),
        "prior_opportunities": prior_opportunities,
    }
    return players, audit, opportunities


def double_play_avoidance_runs(
    events: list[dict[str, Any]],
    prior_opportunities: float = 20.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    opportunities = []
    for event in events:
        if (
            not event.get("is_plate_appearance")
            or int(event["outs_before"]) >= 2
            or not (int(event["bases_before"]) & 1)
            or _batted_ball_type(event.get("play_text") or "") != "ground"
            or not event.get("batter")
        ):
            continue
        position = _primary_fielding_position(event.get("play_text") or "") or "unknown"
        opportunities.append(
            {
                "player": event["batter"],
                "player_key": normalize_person_name(event["batter"]),
                "outs": int(event["outs_before"]),
                "position": position,
                "actual_dp": int(event["event_type"] == "double_play"),
                "run_value": float(event["run_value"]),
            }
        )
    by_outs: dict[int, list[int]] = defaultdict(list)
    by_group: dict[tuple[int, str], list[int]] = defaultdict(list)
    for row in opportunities:
        by_outs[row["outs"]].append(row["actual_dp"])
        by_group[(row["outs"], row["position"])].append(row["actual_dp"])
    dp_values = [row["run_value"] for row in opportunities if row["actual_dp"]]
    other_values = [row["run_value"] for row in opportunities if not row["actual_dp"]]
    dp_cost = max(
        0.25,
        (sum(other_values) / len(other_values) - sum(dp_values) / len(dp_values))
        if dp_values and other_values else 0.5,
    )
    for row in opportunities:
        broad = by_outs[row["outs"]]
        detailed = by_group[(row["outs"], row["position"])]
        broad_rate = sum(broad) / len(broad)
        row["expected_dp"] = (sum(detailed) + prior_opportunities * broad_rate) / (
            len(detailed) + prior_opportunities
        )
        row["raw_runs"] = (row["expected_dp"] - row["actual_dp"]) * dp_cost
    center = sum(row["raw_runs"] for row in opportunities) / len(opportunities) if opportunities else 0.0
    players: dict[str, dict[str, Any]] = {}
    for row in opportunities:
        target = players.setdefault(
            row["player_key"],
            {"player": row["player"], "double_play_opportunities": 0, "actual_double_plays": 0, "expected_double_plays": 0.0, "double_play_avoidance_runs": 0.0},
        )
        target["double_play_opportunities"] += 1
        target["actual_double_plays"] += row["actual_dp"]
        target["expected_double_plays"] += row["expected_dp"]
        target["double_play_avoidance_runs"] += row["raw_runs"] - center
    audit = {
        "opportunities": len(opportunities),
        "actual_double_plays": sum(row["actual_dp"] for row in opportunities),
        "estimated_double_play_run_cost": dp_cost,
        "league_double_play_avoidance_runs": sum(
            row["double_play_avoidance_runs"] for row in players.values()
        ),
        "prior_opportunities": prior_opportunities,
    }
    return players, audit


def arm_runs(
    advancement_opportunities: list[dict[str, Any]],
    shrinkage_opportunities: float = 40.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    eligible = [row for row in advancement_opportunities if row.get("fielder")]
    raw_values = [-row["advancement_runs"] for row in eligible]
    league_center = sum(raw_values) / len(raw_values) if raw_values else 0.0
    players: dict[str, dict[str, Any]] = {}
    for opportunity in eligible:
        fielder = opportunity["fielder"]
        key = normalize_person_name(fielder)
        row = players.setdefault(
            key,
            {
                "player": fielder,
                "teams": set(),
                "arm_opportunities": 0,
                "arm_runs_unshrunk": 0.0,
                "pitcher_arm_opportunities": 0,
                "pitcher_arm_runs_unshrunk": 0.0,
                "non_pitcher_arm_opportunities": 0,
                "non_pitcher_arm_runs_unshrunk": 0.0,
                "arm_runs_opposing_raw": 0.0,
                "attributed_runner_runs": 0.0,
            },
        )
        if opportunity.get("fielding_team"):
            row["teams"].add(opportunity["fielding_team"])
        row["arm_opportunities"] += 1
        row["attributed_runner_runs"] += opportunity["advancement_runs"]
        row["arm_runs_opposing_raw"] -= opportunity["advancement_runs"]
        centered_value = -opportunity["advancement_runs"] - league_center
        row["arm_runs_unshrunk"] += centered_value
        prefix = "pitcher" if opportunity.get("fielding_position") == "pitcher" else "non_pitcher"
        row[f"{prefix}_arm_opportunities"] += 1
        row[f"{prefix}_arm_runs_unshrunk"] += centered_value
    for row in players.values():
        n = row["arm_opportunities"]
        shrinkage = n / (n + shrinkage_opportunities)
        row["arm_runs"] = row["arm_runs_unshrunk"] * shrinkage
        row["pitcher_arm_runs"] = row["pitcher_arm_runs_unshrunk"] * shrinkage
        row["non_pitcher_arm_runs"] = row["non_pitcher_arm_runs_unshrunk"] * shrinkage
        row["teams"] = sorted(row["teams"])
    audit = {
        "advancement_opportunities": len(advancement_opportunities),
        "attributable_arm_opportunities": len(eligible),
        "attribution_coverage": len(eligible) / len(advancement_opportunities) if advancement_opportunities else 0.0,
        "raw_arm_plus_runner_balance": sum(
            row["arm_runs_opposing_raw"] + row["attributed_runner_runs"] for row in players.values()
        ),
        "league_arm_runs_unshrunk_centered": sum(
            row["arm_runs_unshrunk"] for row in players.values()
        ),
        "arm_opportunity_league_center": league_center,
        "league_arm_runs": sum(
            row["arm_runs"] for row in players.values()
        ),
        "shrinkage_opportunities": shrinkage_opportunities,
        "status": "unambiguous single-fielder attribution only",
    }
    return players, audit


def range_runs(
    events: list[dict[str, Any]],
    known_players: list[str],
    conversion_run_value: float,
    shrinkage_opportunities: float = 20.0,
) -> dict[str, dict[str, Any]]:
    opportunities = []
    convertible = {
        "single",
        "double",
        "triple",
        "out",
        "double_play",
        "fielders_choice",
        "reached_on_error",
        "sacrifice_fly",
        "sacrifice_bunt",
        "infield_fly",
    }
    out_results = {"out", "double_play", "fielders_choice", "sacrifice_fly", "sacrifice_bunt", "infield_fly"}
    for event in events:
        if event["event_type"] not in convertible:
            continue
        batted_type = _batted_ball_type(event["play_text"])
        target = _fielding_target(event["play_text"], known_players)
        if not batted_type or not target:
            continue
        position, fielder = target
        opportunities.append(
            {
                "player": fielder,
                "player_key": normalize_person_name(fielder),
                "position": position,
                "batted_type": batted_type,
                "converted": int(event["event_type"] in out_results),
            }
        )
    group_counts: dict[tuple[str, str], list[int]] = defaultdict(list)
    for row in opportunities:
        group_counts[(row["position"], row["batted_type"])].append(row["converted"])
    expected = {key: sum(values) / len(values) for key, values in group_counts.items()}
    players: dict[str, dict[str, Any]] = {}
    for opportunity in opportunities:
        key = opportunity["player_key"]
        row = players.setdefault(
            key,
            {
                "player": opportunity["player"],
                "fielding_opportunities": 0,
                "fielding_runs_unshrunk": 0.0,
                "pitcher_fielding_opportunities": 0,
                "pitcher_fielding_runs_unshrunk": 0.0,
                "non_pitcher_fielding_opportunities": 0,
                "non_pitcher_fielding_runs_unshrunk": 0.0,
                "positions": set(),
            },
        )
        row["fielding_opportunities"] += 1
        row["positions"].add(opportunity["position"])
        probability = expected[(opportunity["position"], opportunity["batted_type"])]
        value = (opportunity["converted"] - probability) * conversion_run_value
        row["fielding_runs_unshrunk"] += value
        prefix = "pitcher" if opportunity["position"] == "pitcher" else "non_pitcher"
        row[f"{prefix}_fielding_opportunities"] += 1
        row[f"{prefix}_fielding_runs_unshrunk"] += value
    for row in players.values():
        n = row["fielding_opportunities"]
        shrinkage = n / (n + shrinkage_opportunities)
        row["range_runs"] = row["fielding_runs_unshrunk"] * shrinkage
        row["pitcher_range_runs"] = row["pitcher_fielding_runs_unshrunk"] * shrinkage
        row["non_pitcher_range_runs"] = row["non_pitcher_fielding_runs_unshrunk"] * shrinkage
        row["positions"] = sorted(row["positions"])
        row["coverage"] = "Position-and-batted-ball-direction model; no coordinates"
    return players


def catcher_throwing_runs(
    stats_rows: list[dict[str, Any]],
    valued_events: list[dict[str, Any]],
    shrinkage_opportunities: float = 20.0,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Center catcher CS/SB value on the season rate and shrink small samples."""
    offense_values = {
        event_type: [
            float(event["run_value"])
            for event in valued_events
            if event.get("event_type") == event_type and event.get("run_value") is not None
        ]
        for event_type in ("stolen_base", "caught_stealing")
    }
    sb_value = (
        sum(offense_values["stolen_base"]) / len(offense_values["stolen_base"])
        if offense_values["stolen_base"] else 0.20
    )
    cs_value = (
        sum(offense_values["caught_stealing"]) / len(offense_values["caught_stealing"])
        if offense_values["caught_stealing"] else -0.45
    )
    outcome_spread = sb_value - cs_value
    catchers: dict[str, dict[str, Any]] = {}
    for source in stats_rows:
        catcher_rows = [row for row in source.get("fieldingStats", []) if row.get("position") == "C"]
        if not catcher_rows:
            continue
        key = canonical_person_key(f"{source.get('firstName', '')} {source.get('lastName', '')}")
        row = catchers.setdefault(
            key,
            {
                "player_key": key,
                "player": f"{source.get('firstName', '')} {source.get('lastName', '')}".strip(),
                "catcher_stolen_bases_allowed": 0,
                "catcher_caught_stealing": 0,
                "catcher_innings": 0.0,
            },
        )
        for fielding in catcher_rows:
            row["catcher_stolen_bases_allowed"] += int(fielding.get("stolenBases") or 0)
            row["catcher_caught_stealing"] += int(fielding.get("caughtStealing") or 0)
            row["catcher_innings"] += float(fielding.get("inningsPlayed") or 0)
    total_sb = sum(row["catcher_stolen_bases_allowed"] for row in catchers.values())
    total_cs = sum(row["catcher_caught_stealing"] for row in catchers.values())
    total_attempts = total_sb + total_cs
    league_cs_rate = total_cs / total_attempts if total_attempts else 0.0
    for row in catchers.values():
        attempts = row["catcher_stolen_bases_allowed"] + row["catcher_caught_stealing"]
        unshrunk = (row["catcher_caught_stealing"] - attempts * league_cs_rate) * outcome_spread
        shrinkage = attempts / (attempts + shrinkage_opportunities) if attempts else 0.0
        row.update(
            {
                "catcher_steal_attempts": attempts,
                "catcher_cs_rate": row["catcher_caught_stealing"] / attempts if attempts else 0.0,
                "catcher_throwing_runs_unshrunk": unshrunk,
                "catcher_throwing_runs": unshrunk * shrinkage,
            }
        )
    shrinkage_center = (
        sum(row["catcher_throwing_runs"] for row in catchers.values()) / total_attempts
        if total_attempts else 0.0
    )
    for row in catchers.values():
        row["catcher_throwing_runs"] -= row["catcher_steal_attempts"] * shrinkage_center
    return catchers, {
        "catchers": len(catchers),
        "stolen_bases_allowed": total_sb,
        "caught_stealing": total_cs,
        "attempts": total_attempts,
        "league_caught_stealing_rate": league_cs_rate,
        "stolen_base_offense_run_value": sb_value,
        "caught_stealing_offense_run_value": cs_value,
        "outcome_run_value_spread": outcome_spread,
        "shrinkage_opportunities": shrinkage_opportunities,
        "post_shrinkage_center_per_attempt": shrinkage_center,
        "league_catcher_throwing_runs": sum(row["catcher_throwing_runs"] for row in catchers.values()),
    }


def add_fip(
    pitching_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Add traditional FIP on a seven-inning scale with a season-specific constant."""
    by_pitcher: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        if not event.get("is_plate_appearance") or not event.get("pitcher"):
            continue
        key = event.get("pitcher_key") or canonical_person_key(event["pitcher"])
        values = by_pitcher[key]
        event_type = event.get("event_type")
        values["BF"] += 1
        values["HR"] += int(event_type == "home_run")
        values["BB"] += int(event_type in {"walk", "intentional_walk"})
        values["HBP"] += int(event_type == "hit_by_pitch")
        values["SO"] += int(
            event_type in {"strikeout", "dropped_third_out", "dropped_third_reached"}
        )

    total_ip = sum(float(row["IP"]) for row in pitching_rows)
    league_era = (
        sum(float(row["ER"]) for row in pitching_rows) / total_ip * 7 if total_ip else 0.0
    )
    league_counts = Counter()
    for counts in by_pitcher.values():
        league_counts.update(counts)
    seven_inning_scale = 7 / 9
    league_component = seven_inning_scale * (
        13 * league_counts["HR"]
        + 3 * (league_counts["BB"] + league_counts["HBP"])
        - 2 * league_counts["SO"]
    ) / total_ip
    fip_constant = league_era - league_component
    for pitcher in pitching_rows:
        counts = by_pitcher.get(pitcher["player_key"], Counter())
        ip = float(pitcher["IP"])
        era = float(pitcher["ER"]) / float(pitcher["IP"]) * 7
        component = seven_inning_scale * (
            13 * counts["HR"]
            + 3 * (counts["BB"] + counts["HBP"])
            - 2 * counts["SO"]
        ) / ip
        fip = component + fip_constant
        pitcher.update(
            {
                "ERA": era,
                "FIP": fip,
                "ERA_minus_FIP": era - fip,
                "FIP_BF": counts["BF"],
                "FIP_HR": counts["HR"],
                "FIP_BB": counts["BB"],
                "FIP_HBP": counts["HBP"],
                "FIP_SO": counts["SO"],
            }
        )
    return {
        "scale": "runs per seven innings",
        "league_era": league_era,
        "seven_inning_scale": seven_inning_scale,
        "constant": fip_constant,
        "league_component_before_constant": league_component,
        "league_HR": league_counts["HR"],
        "league_BB": league_counts["BB"],
        "league_HBP": league_counts["HBP"],
        "league_SO": league_counts["SO"],
        "league_IP": total_ip,
        "war_inclusion": False,
    }


def aggregate_pitching(
    events: list[dict[str, Any]],
    boxscore_rows: list[dict[str, Any]],
    games_played: int,
    runs_per_win: float,
    season: int = 2026,
    official_team_runs: dict[str, int] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    starters: set[tuple[str, str, str]] = set()
    seen_game_team: set[tuple[str, str]] = set()
    for source in boxscore_rows:
        if source["season"] != season or source["role"] != "pitching":
            continue
        team = display_team(source["team"], season)
        key = canonical_person_key(source["player"])
        game_team = (source["canonical_id"], team)
        if game_team not in seen_game_team:
            starters.add((source["canonical_id"], team, key))
            seen_game_team.add(game_team)
        row = rows.setdefault(
            key,
            {
                "player_key": key,
                "player": source["player"],
                "teams": set(),
                "pitching_outs": 0,
                "H_allowed": 0,
                "R_allowed": 0,
                "ER": 0,
                "BB_allowed": 0,
                "SO_pitching": 0,
                "G": 0,
                "GS": 0,
            },
        )
        row["teams"].add(team)
        row["pitching_outs"] += round(float(source["innings_decimal"]) * 3)
        row["H_allowed"] += _number(source.get("H"))
        row["R_allowed"] += _number(source.get("R"))
        row["ER"] += _number(source.get("ER"))
        row["BB_allowed"] += _number(source.get("BB"))
        row["SO_pitching"] += _number(source.get("SO"))
        row["G"] += 1
        row["GS"] += int((source["canonical_id"], team, key) in starters)

    team_runs: Counter[str] = Counter()
    team_pa: Counter[str] = Counter()
    pitcher_opponents: dict[str, Counter[str]] = defaultdict(Counter)
    for event in events:
        if event["season"] != season or not event.get("is_plate_appearance"):
            continue
        team = display_team(event["batting_team"], season)
        team_pa[team] += 1
        if event.get("pitcher"):
            pitcher_opponents[canonical_person_key(event["pitcher"])][team] += 1

    if official_team_runs is not None:
        team_runs.update(official_team_runs)
    else:
        for event in events:
            if event["season"] == season:
                team_runs[display_team(event["batting_team"], season)] += int(
                    event.get("runs_scored", 0) or 0
                )

    league_outs = sum(row["pitching_outs"] for row in rows.values())
    league_ip = league_outs / 3
    league_runs = sum(row["R_allowed"] for row in rows.values())
    league_ra7 = league_runs / league_ip * 7
    league_pa = sum(team_pa.values())
    league_runs_per_pa = sum(team_runs.values()) / league_pa
    opponent_prior_pa = 200.0
    team_rates = {
        team: (team_runs[team] + opponent_prior_pa * league_runs_per_pa)
        / (team_pa[team] + opponent_prior_pa)
        for team in team_pa
    }
    replacement_wins = games_played * (1000 / 2430) * 0.43
    replacement_runs_per_ip = replacement_wins * runs_per_win / league_ip

    preliminary = []
    for key, row in rows.items():
        ip = row["pitching_outs"] / 3
        if ip <= 0:
            continue
        ra7 = row["R_allowed"] / ip * 7
        opponents = pitcher_opponents.get(key, Counter())
        batters_faced = sum(opponents.values())
        opponent_rate = (
            sum(team_rates[team] * count for team, count in opponents.items()) / batters_faced
            if batters_faced else league_runs_per_pa
        )
        opponent_ra7 = league_ra7 * opponent_rate / league_runs_per_pa
        raw_raa = (opponent_ra7 - ra7) / 7 * ip
        row.update(
            {
                "IP": ip,
                "RA7": ra7,
                "batters_faced_from_play_by_play": batters_faced,
                "opponent_expected_RA7": opponent_ra7,
                "opponent_strength_adjustment_runs": (opponent_ra7 - league_ra7) / 7 * ip,
                "pitching_runs_above_average_raw": raw_raa,
            }
        )
        row["teams"] = sorted(row["teams"])
        preliminary.append(row)
    league_correction_per_ip = -sum(
        row["pitching_runs_above_average_raw"] for row in preliminary
    ) / league_ip
    for row in preliminary:
        raa = row["pitching_runs_above_average_raw"] + league_correction_per_ip * row["IP"]
        replacement_runs = replacement_runs_per_ip * row["IP"]
        row["pitching_runs_above_average"] = raa
        row["pitching_replacement_runs"] = replacement_runs
        row["pitching_war"] = (raa + replacement_runs) / runs_per_win
    constants = {
        "league_ip": league_ip,
        "league_ra7": league_ra7,
        "opponent_strength_prior_pa": opponent_prior_pa,
        "opponent_team_runs_per_pa": team_rates,
        "league_correction_runs_per_ip": league_correction_per_ip,
        "replacement_pitcher_wins": replacement_wins,
        "replacement_runs_per_ip": replacement_runs_per_ip,
        "leverage_adjustment": "unavailable",
    }
    return preliminary, constants


def _build_war_season(
    project_root: Path,
    snapshot_id: str,
    season: int,
    valued_events: list[dict[str, Any]],
    full_events: list[dict[str, Any]],
    re24_rows: list[dict[str, Any]],
    boxscore_rows: list[dict[str, Any]],
    supplemental_audit: list[dict[str, Any]],
) -> dict[str, Any]:
    games_2026 = len(completed_schedule(project_root, snapshot_id, season))
    events_2026 = [event for event in valued_events if event["season"] == season]
    full_events_2026 = [event for event in full_events if event["season"] == season]
    stats_rows = official_stats(project_root, snapshot_id, season)
    for event in full_events_2026:
        event["batting_team"] = display_team(event["batting_team"], season)
        event["fielding_team"] = display_team(event["fielding_team"], season)
        if event.get("batter"):
            event["batter_key"] = canonical_person_key(event["batter"])
        if event.get("pitcher"):
            event["pitcher_key"] = canonical_person_key(event["pitcher"])
    for event in events_2026:
        event["batting_team"] = display_team(event["batting_team"], season)
        event["fielding_team"] = display_team(event["fielding_team"], season)

    constants = derive_woba_constants(valued_events, target_events=full_events_2026)
    offense = aggregate_offense(full_events_2026, constants)
    offense_team = aggregate_offense(full_events_2026, constants, group_by_team=True)
    official_names = {
        canonical_person_key(f"{row.get('firstName', '')} {row.get('lastName', '')}"):
        f"{row.get('firstName', '')} {row.get('lastName', '')}".strip()
        for row in stats_rows
        if row.get("firstName") and row.get("lastName")
    }
    for row in offense:
        row["player"] = official_names.get(row["player_key"], row["player"])
    known_players = sorted(
        {row["player"] for row in offense}
        | {
            row["player"]
            for row in boxscore_rows
            if row["season"] == season and row.get("player")
        },
        key=len,
        reverse=True,
    )
    baserunning, baserunning_audit, advancement_opportunities = expanded_baserunning_runs(
        events_2026, offense, re24_rows, known_players
    )
    double_plays, double_play_audit = double_play_avoidance_runs(events_2026)
    arm, arm_audit = arm_runs(advancement_opportunities)
    conversion_value = constants["raw_weights"]["single"]
    fielding = range_runs(events_2026, known_players, conversion_value)
    catcher, catcher_audit = catcher_throwing_runs(stats_rows, valued_events)
    baserunning = _canonicalize_component_map(baserunning)
    double_plays = _canonicalize_component_map(double_plays)
    arm = _canonicalize_component_map(arm)
    fielding = _canonicalize_component_map(fielding)
    offense_keys = {row["player_key"] for row in offense}
    component_keys = set(baserunning) | set(double_plays) | set(fielding) | set(arm) | set(catcher)
    teams_by_key: dict[str, set[str]] = defaultdict(set)
    for box_row in boxscore_rows:
        if box_row["season"] == season and box_row.get("team"):
            teams_by_key[canonical_person_key(box_row["player"])].add(
                display_team(box_row["team"], season)
            )
    for key in sorted(component_keys - offense_keys):
        source = (
            baserunning.get(key)
            or arm.get(key)
            or fielding.get(key)
            or double_plays.get(key)
            or catcher.get(key)
            or {}
        )
        offense.append(
            _empty_offense_row(
                key,
                source.get("player", key),
                sorted(teams_by_key.get(key, set()) | set(source.get("teams", []))),
            )
        )

    official_runs = team_run_totals(project_root, snapshot_id, season)
    total_runs = sum(official_runs.values())
    league_ip = sum(
        float(row["innings_decimal"])
        for row in boxscore_rows
        if row["season"] == season and row["role"] == "pitching"
    )
    league_ra7 = total_runs / league_ip * 7
    runs_per_win = 1.5 * league_ra7 + 3
    league_pa = sum(row["PA"] for row in offense)
    position_replacement_wins = games_2026 * (1000 / 2430) * 0.57
    replacement_runs_per_pa = position_replacement_wins * runs_per_win / league_pa

    total_pre_league = sum(
        row["batting_runs"]
        + baserunning.get(row["player_key"], {}).get("baserunning_runs", 0.0)
        + double_plays.get(row["player_key"], {}).get("double_play_avoidance_runs", 0.0)
        + fielding.get(row["player_key"], {}).get("non_pitcher_range_runs", 0.0)
        + arm.get(row["player_key"], {}).get("non_pitcher_arm_runs", 0.0)
        + catcher.get(row["player_key"], {}).get("catcher_throwing_runs", 0.0)
        for row in offense
    )
    league_runs_per_pa = -total_pre_league / league_pa

    position_rows = []
    for row in offense:
        key = row["player_key"]
        bsr = baserunning.get(key, {})
        dp = double_plays.get(key, {})
        fld = fielding.get(key, {})
        arm_row = arm.get(key, {})
        catcher_row = catcher.get(key, {})
        league_runs = league_runs_per_pa * row["PA"]
        replacement_runs = replacement_runs_per_pa * row["PA"]
        hitting_runs = row["batting_runs"]
        baserunning_component_runs = (
            bsr.get("baserunning_runs", 0.0)
            + dp.get("double_play_avoidance_runs", 0.0)
        )
        range_runs_value = fld.get("non_pitcher_range_runs", 0.0)
        arm_runs_value = arm_row.get("non_pitcher_arm_runs", 0.0)
        catcher_throwing_runs_value = catcher_row.get("catcher_throwing_runs", 0.0)
        defense_runs = range_runs_value + arm_runs_value + catcher_throwing_runs_value
        positional_adjustment_runs = 0.0
        defense_component_runs = defense_runs + positional_adjustment_runs
        offensive_component_runs = (
            hitting_runs + baserunning_component_runs + league_runs + replacement_runs
        )
        position_rar = (
            hitting_runs
            + baserunning_component_runs
            + defense_component_runs
            + league_runs
            + replacement_runs
        )
        row.update(
            {
                "baserunning_runs": bsr.get("baserunning_runs", 0.0),
                "sb_cs_runs": bsr.get("sb_cs_runs", 0.0),
                "non_steal_advancement_runs": bsr.get("non_steal_advancement_runs", 0.0),
                "runner_advancement_runs": bsr.get("runner_advancement_runs", 0.0),
                "batter_advancement_runs": bsr.get("batter_advancement_runs", 0.0),
                "sb_cs_attempts": bsr.get("sb_cs_attempts", 0),
                "advancement_opportunities": bsr.get("advancement_opportunities", 0),
                "double_play_avoidance_runs": dp.get("double_play_avoidance_runs", 0.0),
                "double_play_opportunities": dp.get("double_play_opportunities", 0),
                "actual_double_plays": dp.get("actual_double_plays", 0),
                "expected_double_plays": dp.get("expected_double_plays", 0.0),
                "range_runs": range_runs_value,
                "fielding_opportunities": fld.get("non_pitcher_fielding_opportunities", 0),
                "arm_runs": arm_runs_value,
                "arm_runs_unshrunk": arm_row.get("non_pitcher_arm_runs_unshrunk", 0.0),
                "arm_opportunities": arm_row.get("non_pitcher_arm_opportunities", 0),
                "catcher_stolen_bases_allowed": catcher_row.get("catcher_stolen_bases_allowed", 0),
                "catcher_caught_stealing": catcher_row.get("catcher_caught_stealing", 0),
                "catcher_steal_attempts": catcher_row.get("catcher_steal_attempts", 0),
                "catcher_cs_rate": catcher_row.get("catcher_cs_rate", 0.0),
                "catcher_throwing_runs": catcher_throwing_runs_value,
                "throwing_runs": arm_runs_value + catcher_throwing_runs_value,
                "positional_adjustment_runs": positional_adjustment_runs,
                "league_adjustment_runs": league_runs,
                "position_replacement_runs": replacement_runs,
                "hitting_runs": hitting_runs,
                "wRAA": hitting_runs,
                "batting_war": hitting_runs / runs_per_win,
                "baserunning_component_runs": baserunning_component_runs,
                "baserunning_war": baserunning_component_runs / runs_per_win,
                "defense_runs": defense_runs,
                "defense_war": defense_component_runs / runs_per_win,
                "defensive_war": defense_component_runs / runs_per_win,
                "offensive_war": offensive_component_runs / runs_per_win,
                "position_war": position_rar / runs_per_win,
            }
        )
        position_rows.append(row)

    pitching_rows, pitching_constants = aggregate_pitching(
        full_events_2026,
        boxscore_rows,
        games_2026,
        runs_per_win,
        season=season,
        official_team_runs=official_runs,
    )
    for pitcher in pitching_rows:
        pitcher["player"] = official_names.get(pitcher["player_key"], pitcher["player"])
    for pitcher in pitching_rows:
        key = pitcher["player_key"]
        fld = fielding.get(key, {})
        arm_row = arm.get(key, {})
        pitcher_range_runs = fld.get("pitcher_range_runs", 0.0)
        pitcher_arm_runs = arm_row.get("pitcher_arm_runs", 0.0)
        pitcher_defense_runs = pitcher_range_runs + pitcher_arm_runs
        pitcher_defense_war = pitcher_defense_runs / runs_per_win
        ra7_raa = pitcher["pitching_runs_above_average"]
        ra7_war = pitcher["pitching_war"]
        pitcher.update(
            {
                "ra7_pitching_runs_above_average": ra7_raa,
                "pitching_runs_above_average": ra7_raa - pitcher_defense_runs,
                "pitcher_range_runs": pitcher_range_runs,
                "pitcher_arm_runs": pitcher_arm_runs,
                "pitcher_defense_runs": pitcher_defense_runs,
                "pitcher_defense_war": pitcher_defense_war,
                "pitcher_war": ra7_war,
                "pitching_war": ra7_war - pitcher_defense_war,
            }
        )
    fip_audit = add_fip(pitching_rows, full_events_2026)
    positions = {row["player_key"]: row for row in position_rows}
    pitchers = {row["player_key"]: row for row in pitching_rows}
    combined_rows = []
    for key in sorted(set(positions) | set(pitchers)):
        position = positions.get(key, {})
        pitcher = pitchers.get(key, {})
        combined_rows.append(
            {
                "player_key": key,
                "player": position.get("player") or pitcher.get("player"),
                "teams": sorted(set(position.get("teams", [])) | set(pitcher.get("teams", []))),
                "PA": position.get("PA", 0),
                "IP": pitcher.get("IP", 0.0),
                "batting_runs": position.get("batting_runs", 0.0),
                "hitting_runs": position.get("hitting_runs", 0.0),
                "wRAA": position.get("wRAA", 0.0),
                "batting_war": position.get("batting_war", 0.0),
                "baserunning_runs": position.get("baserunning_runs", 0.0),
                "baserunning_component_runs": position.get("baserunning_component_runs", 0.0),
                "baserunning_war": position.get("baserunning_war", 0.0),
                "sb_cs_runs": position.get("sb_cs_runs", 0.0),
                "non_steal_advancement_runs": position.get("non_steal_advancement_runs", 0.0),
                "runner_advancement_runs": position.get("runner_advancement_runs", 0.0),
                "batter_advancement_runs": position.get("batter_advancement_runs", 0.0),
                "advancement_opportunities": position.get("advancement_opportunities", 0),
                "double_play_avoidance_runs": position.get("double_play_avoidance_runs", 0.0),
                "double_play_opportunities": position.get("double_play_opportunities", 0),
                "range_runs": position.get("range_runs", 0.0),
                "arm_runs": position.get("arm_runs", 0.0),
                "catcher_stolen_bases_allowed": position.get("catcher_stolen_bases_allowed", 0),
                "catcher_caught_stealing": position.get("catcher_caught_stealing", 0),
                "catcher_steal_attempts": position.get("catcher_steal_attempts", 0),
                "catcher_cs_rate": position.get("catcher_cs_rate", 0.0),
                "catcher_throwing_runs": position.get("catcher_throwing_runs", 0.0),
                "throwing_runs": position.get("throwing_runs", 0.0),
                "defense_runs": position.get("defense_runs", 0.0),
                "defense_war": position.get("defense_war", 0.0),
                "defensive_war": position.get("defensive_war", 0.0),
                "offensive_war": position.get("offensive_war", 0.0),
                "arm_opportunities": position.get("arm_opportunities", 0),
                "positional_adjustment_runs": position.get("positional_adjustment_runs", 0.0),
                "league_adjustment_runs": position.get("league_adjustment_runs", 0.0),
                "position_replacement_runs": position.get("position_replacement_runs", 0.0),
                "position_war": position.get("position_war", 0.0),
                "RA7": pitcher.get("RA7", 0.0),
                "ERA": pitcher.get("ERA", 0.0),
                "FIP": pitcher.get("FIP", 0.0),
                "ERA_minus_FIP": pitcher.get("ERA_minus_FIP", 0.0),
                "FIP_BF": pitcher.get("FIP_BF", 0),
                "opponent_expected_RA7": pitcher.get("opponent_expected_RA7", 0.0),
                "pitching_runs_above_average": pitcher.get("pitching_runs_above_average", 0.0),
                "ra7_pitching_runs_above_average": pitcher.get("ra7_pitching_runs_above_average", 0.0),
                "pitching_war": pitcher.get("pitching_war", 0.0),
                "pitcher_range_runs": pitcher.get("pitcher_range_runs", 0.0),
                "pitcher_arm_runs": pitcher.get("pitcher_arm_runs", 0.0),
                "pitcher_defense_runs": pitcher.get("pitcher_defense_runs", 0.0),
                "pitcher_defense_war": pitcher.get("pitcher_defense_war", 0.0),
                "pitcher_war": pitcher.get("pitcher_war", 0.0),
                "total_war": position.get("position_war", 0.0)
                + pitcher.get("pitcher_war", 0.0),
                "quality_flags": _quality_flags(position, pitcher),
            }
        )

    model_constants = {
        "snapshot_id": snapshot_id,
        "season": season,
        "completed_games": games_2026,
        "league_runs": total_runs,
        "league_ip": league_ip,
        "league_ra7": league_ra7,
        "runs_per_win": runs_per_win,
        "park_factor": 1.0,
        "woba": constants,
        "position_replacement_wins": position_replacement_wins,
        "replacement_runs_per_pa": replacement_runs_per_pa,
        "pitching": pitching_constants,
        "baserunning": baserunning_audit,
        "double_play_avoidance": double_play_audit,
        "arm_value": arm_audit,
        "catcher_throwing": catcher_audit,
        "fip": fip_audit,
        "official_supplemental_games": [
            row for row in supplemental_audit if row["season"] == season
        ],
    }
    output = project_root / "output"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / f"model_constants_{season}.json", model_constants)
    write_json(output / f"position_players_{season}.json", position_rows)
    write_json(output / f"baserunning_{season}.json", list(baserunning.values()))
    write_json(output / f"double_play_avoidance_{season}.json", list(double_plays.values()))
    write_json(output / f"arm_value_{season}.json", list(arm.values()))
    write_json(output / f"catcher_throwing_{season}.json", list(catcher.values()))
    write_json(output / f"advancement_opportunities_{season}.json", advancement_opportunities)
    write_json(output / f"pitchers_{season}.json", pitching_rows)
    write_json(output / f"combined_{season}.json", combined_rows)
    write_json(output / f"position_player_team_splits_{season}.json", offense_team)
    _write_csv(output / f"position_player_team_splits_{season}.csv", offense_team)
    _write_csv(output / f"baserunning_{season}.csv", list(baserunning.values()))
    _write_csv(output / f"double_play_avoidance_{season}.csv", list(double_plays.values()))
    _write_csv(output / f"arm_value_{season}.csv", list(arm.values()))
    _write_csv(output / f"catcher_throwing_{season}.csv", list(catcher.values()))
    _write_csv(output / f"position_players_{season}.csv", position_rows)
    _write_csv(output / f"pitchers_{season}.csv", pitching_rows)
    _write_csv(output / f"ausl_{season}_war.csv", combined_rows)
    _write_leaderboard(output / f"ausl_{season}_war.md", combined_rows, season)
    if season == 2026:
        write_json(output / "model_constants.json", model_constants)
        _write_impact_report(output, combined_rows)
    summary = {
        "snapshot_id": snapshot_id,
        "season": season,
        "completed_games": games_2026,
        "position_players": len(position_rows),
        "pitchers": len(pitching_rows),
        "combined_players": len(combined_rows),
        "runs_per_win": runs_per_win,
        "league_position_batting_runs": sum(row["batting_runs"] for row in position_rows),
        "league_baserunning_runs": sum(row["baserunning_runs"] for row in position_rows),
        "league_non_steal_advancement_runs": sum(
            row["non_steal_advancement_runs"] for row in position_rows
        ),
        "league_double_play_avoidance_runs": sum(
            row["double_play_avoidance_runs"] for row in position_rows
        ),
        "league_range_runs": sum(
            row["range_runs"] for row in position_rows
        ),
        "league_arm_runs": sum(
            row["arm_runs"] for row in position_rows
        ),
        "league_catcher_throwing_runs": sum(
            row["catcher_throwing_runs"] for row in position_rows
        ),
        "league_adjusted_position_raa": sum(
            row["batting_runs"]
            + row["baserunning_runs"]
            + row["double_play_avoidance_runs"]
            + row["range_runs"]
            + row["arm_runs"]
            + row["catcher_throwing_runs"]
            + row["league_adjustment_runs"]
            for row in position_rows
        ),
        "position_war_total": sum(
            row["position_war"] for row in position_rows
        ),
        "pitching_war_total": sum(row["pitcher_war"] for row in pitching_rows),
        "pitching_component_war_total": sum(row["pitching_war"] for row in pitching_rows),
        "pitcher_defense_war_total": sum(row["pitcher_defense_war"] for row in pitching_rows),
        "total_war": sum(row["total_war"] for row in combined_rows),
    }
    write_json(output / f"war_summary_{season}.json", summary)
    return summary


def build_war_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    valued_events = read_json(snapshot / "model" / "valued_events.json")
    re24_rows = read_json(snapshot / "model" / "re24.json")
    base_boxscore_rows = read_json(snapshot / "normalized" / "player_game_boxscore.json")
    supplemental_rows, supplemental_audit = supplemental_boxscore_rows(
        project_root, snapshot_id, base_boxscore_rows
    )
    boxscore_rows = base_boxscore_rows + supplemental_rows
    supplemental_events, supplemental_event_audit = supplemental_normalized_events(
        project_root, snapshot_id, supplemental_audit
    )
    valued_events.extend(value_supplemental_events(supplemental_events, re24_rows))
    full_events = read_json(project_root / "output" / "tto" / "plate_appearances.json")
    output = project_root / "output"
    write_json(output / "official_supplemental_game_audit.json", supplemental_audit)
    write_json(output / "official_supplemental_event_audit.json", supplemental_event_audit)
    write_json(output / "official_supplemental_events.json", supplemental_events)
    summaries = {
        str(season): _build_war_season(
            project_root,
            snapshot_id,
            season,
            valued_events,
            full_events,
            re24_rows,
            boxscore_rows,
            supplemental_audit,
        )
        for season in (2025, 2026)
    }
    combined = {
        "snapshot_id": snapshot_id,
        "seasons": summaries,
        "supplemental_games": len(supplemental_audit),
    }
    write_json(output / "war_summary.json", combined)
    return combined


def _quality_flags(position: dict[str, Any], pitcher: dict[str, Any]) -> list[str]:
    flags = []
    if 0 < position.get("PA", 0) < 20:
        flags.append("small_position_player_sample")
    if 0 < pitcher.get("IP", 0) < 5:
        flags.append("small_pitching_sample")
    if position:
        flags.append("no_positional_adjustment")
    if pitcher:
        flags.append("no_reliever_leverage_adjustment")
    return flags


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "|".join(value) if isinstance(value, list) else value
                    for key, value in row.items()
                }
            )


def _write_leaderboard(path: Path, rows: list[dict[str, Any]], season: int) -> None:
    leaders = sorted(rows, key=lambda row: row["total_war"], reverse=True)
    lines = [
        f"# AUSL {season} WAR Research Leaderboard",
        "",
        "Research output through the snapshot date. Total WAR is Position WAR plus results-based Pitching WAR.",
        "",
        "| Rank | Player | Team(s) | PA | IP | Position WAR | Pitcher WAR | Total WAR |",
        "|---:|---|---|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(leaders, 1):
        lines.append(
            f"| {rank} | {row['player']} | {', '.join(row['teams'])} | {row['PA']} | "
            f"{row['IP']:.1f} | {row['position_war']:.2f} | "
            f"{row['pitcher_war']:.2f} | {row['total_war']:.2f} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_impact_report(output: Path, current: list[dict[str, Any]]) -> None:
    baseline_path = output / "baseline_pre_runner_fix" / "combined_2026.json"
    if not baseline_path.exists():
        return
    baseline = {row["player_key"]: row for row in read_json(baseline_path)}
    rows = []
    for row in current:
        old = baseline.get(row["player_key"], {})
        old_total = float(old.get("combined_war_experimental_fip", 0.0))
        old_position = float(old.get("position_war_experimental", 0.0))
        rows.append(
            {
                "player_key": row["player_key"],
                "player": row["player"],
                "teams": row["teams"],
                "old_position_war": old_position,
                "new_position_war": row["position_war"],
                "position_war_change": row["position_war"] - old_position,
                "old_total_war": old_total,
                "new_total_war": row["total_war"],
                "total_war_change": row["total_war"] - old_total,
                "sb_cs_runs": row["sb_cs_runs"],
                "non_steal_advancement_runs": row["non_steal_advancement_runs"],
                "double_play_avoidance_runs": row["double_play_avoidance_runs"],
                "arm_runs": row["arm_runs"],
            }
        )
    rows.sort(key=lambda row: abs(row["total_war_change"]), reverse=True)
    write_json(output / "old_vs_new_player_impact.json", rows)
    _write_csv(output / "old_vs_new_player_impact.csv", rows)
    lines = [
        "# AUSL WAR Old-vs-New Player Impact",
        "",
        "Comparison against the preserved July 4 output before the runner-state correction and expanded baserunning model.",
        "",
        "| Player | Old total | New total | Change | Non-steal BsR | DP runs | Arm runs |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows[:30]:
        lines.append(
            f"| {row['player']} | {row['old_total_war']:.2f} | "
            f"{row['new_total_war']:.2f} | {row['total_war_change']:+.2f} | "
            f"{row['non_steal_advancement_runs']:+.2f} | {row['double_play_avoidance_runs']:+.2f} | "
            f"{row['arm_runs']:+.2f} |"
        )
    (output / "old_vs_new_player_impact.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )
