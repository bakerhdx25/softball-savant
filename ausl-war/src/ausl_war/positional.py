from __future__ import annotations

import csv
import itertools
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .io import read_json, write_json
from .normalize import normalize_person_name
from .war import _batted_ball_type, _fielding_target


STANDARD_POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
POSITION_NAMES = {
    "catcher": "C",
    "first baseman": "1B",
    "second baseman": "2B",
    "third baseman": "3B",
    "shortstop": "SS",
    "left fielder": "LF",
    "center fielder": "CF",
    "right fielder": "RF",
}
SUBSTITUTION_RE = re.compile(r"lineup changed|courtesy runner", re.I)
TEAM_FAMILY = {
    "AUSL Blaze": "Carolina Blaze",
    "AUSL Bandits": "Chicago Bandits",
    "AUSL Talons": "Utah Talons",
    "AUSL Volts": "Texas Volts",
}
OUT_RESULTS = {
    "out", "double_play", "fielders_choice", "sacrifice_fly",
    "sacrifice_bunt", "infield_fly",
}


def split_positions(value: str | None) -> list[str]:
    return [part.strip().upper() for part in (value or "").split(",") if part.strip()]


def team_family(team: str) -> str:
    return TEAM_FAMILY.get(team, team)


def center_position_scale(values: dict[str, float], weights: dict[str, float]) -> dict[str, float]:
    denominator = sum(weights.get(position, 0.0) for position in values)
    center = (
        sum(values[position] * weights.get(position, 0.0) for position in values) / denominator
        if denominator else 0.0
    )
    return {position: value - center for position, value in values.items()}


def weighted_player_adjustment(
    outs_by_position: dict[str, float],
    runs_per_175_innings: dict[str, float],
) -> float:
    return sum(
        runs_per_175_innings.get(position, 0.0) * outs / (175.0 * 3.0)
        for position, outs in outs_by_position.items()
    )


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted({key for row in rows for key in row})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _team_outs(events: list[dict[str, Any]]) -> Counter[tuple[str, str]]:
    result: Counter[tuple[str, str]] = Counter()
    for event in events:
        gained = max(0, int(event["outs_after"]) - int(event["outs_before"]))
        result[(event["canonical_id"], event["fielding_team"])] += gained
    return result


def build_position_exposure(
    boxscore_rows: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[tuple[str, str], list[str]]]:
    hitting = [row for row in boxscore_rows if row["role"] == "hitting"]
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    game_names: dict[str, list[str]] = defaultdict(list)
    for row in hitting:
        groups[(row["canonical_id"], row["team"])].append(row)
        game_names[row["canonical_id"]].append(row["player"])

    games_with_any_substitution = {
        event["canonical_id"]
        for event in events
        if SUBSTITUTION_RE.search(event.get("pitch_text", ""))
    }
    outs = _team_outs(events)
    exposure: dict[tuple[int, str, str, str], dict[str, Any]] = {}
    team_game_audit = []
    position_map: dict[tuple[str, str], list[str]] = {}

    for (game_id, team), rows in groups.items():
        assignments: dict[str, list[dict[str, Any]]] = defaultdict(list)
        multi_position = False
        for row in rows:
            positions = [p for p in split_positions(row.get("position")) if p in STANDARD_POSITIONS]
            position_map[(game_id, row["player_key"])] = positions
            multi_position |= len(positions) > 1
            for position in positions:
                assignments[position].append(row)
        complete = set(assignments) == set(STANDARD_POSITIONS)
        unique = complete and all(len(assignments[p]) == 1 for p in STANDARD_POSITIONS)
        no_substitutions = game_id not in games_with_any_substitution
        confirmed = unique and not multi_position and no_substitutions
        team_outs = outs[(game_id, team)]
        team_game_audit.append(
            {
                "canonical_id": game_id,
                "team": team,
                "season": rows[0]["season"],
                "defensive_outs": team_outs,
                "complete_standard_positions": complete,
                "unique_standard_assignments": unique,
                "multi_position_player": multi_position,
                "game_has_recorded_substitution": not no_substitutions,
                "confirmed_for_innings": confirmed,
            }
        )
        for position, assigned_rows in assignments.items():
            for row in assigned_rows:
                key = (row["season"], row["player_key"], team, position)
                target = exposure.setdefault(
                    key,
                    {
                        "season": row["season"],
                        "player_key": row["player_key"],
                        "player": row["player"],
                        "team": team,
                        "position": position,
                        "position_game_labels": 0,
                        "confirmed_defensive_outs": 0,
                        "ambiguous_position_games": 0,
                        "fielding_mentions": 0,
                    },
                )
                target["position_game_labels"] += 1
                if confirmed:
                    target["confirmed_defensive_outs"] += team_outs
                else:
                    target["ambiguous_position_games"] += 1

    mention_counts: Counter[tuple[int, str, str, str]] = Counter()
    teams_by_game_player = {
        (row["canonical_id"], row["player_key"]): row["team"] for row in hitting
    }
    for event in events:
        target = _fielding_target(event.get("play_text", ""), game_names[event["canonical_id"]])
        if not target:
            continue
        long_position, player = target
        if long_position not in POSITION_NAMES:
            continue
        position = POSITION_NAMES[long_position]
        player_key = normalize_person_name(player)
        team = teams_by_game_player.get((event["canonical_id"], player_key), event["fielding_team"])
        mention_counts[(event["season"], player_key, team, position)] += 1
    for key, count in mention_counts.items():
        if key in exposure:
            exposure[key]["fielding_mentions"] += count

    rows = sorted(exposure.values(), key=lambda row: (row["season"], row["player"], row["position"]))
    for row in rows:
        row["confirmed_defensive_innings"] = row["confirmed_defensive_outs"] / 3
        row["coverage_status"] = (
            "confirmed_clean_team_games_only"
            if row["confirmed_defensive_outs"] else "position_label_only_no_defensive_innings"
        )
    total_required_outs = sum(row["defensive_outs"] * len(STANDARD_POSITIONS) for row in team_game_audit)
    confirmed_outs = sum(
        row["defensive_outs"] * len(STANDARD_POSITIONS)
        for row in team_game_audit if row["confirmed_for_innings"]
    )
    audit = {
        "team_games": len(team_game_audit),
        "games": len({row["canonical_id"] for row in team_game_audit}),
        "team_games_with_confirmed_position_innings": sum(row["confirmed_for_innings"] for row in team_game_audit),
        "games_with_any_recorded_substitution": len(games_with_any_substitution),
        "team_games_with_complete_standard_position_labels": sum(row["complete_standard_positions"] for row in team_game_audit),
        "team_games_with_unique_standard_assignments": sum(row["unique_standard_assignments"] for row in team_game_audit),
        "confirmed_standard_position_outs": confirmed_outs,
        "possible_standard_position_outs": total_required_outs,
        "confirmed_position_innings_coverage": confirmed_outs / total_required_outs if total_required_outs else 0.0,
        "team_game_details": team_game_audit,
    }
    return rows, audit, position_map


def _event_type_weights(events: list[dict[str, Any]]) -> dict[int, dict[str, float]]:
    values: dict[int, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for event in events:
        if event.get("is_plate_appearance"):
            values[event["season"]][event["event_type"]].append(float(event.get("run_value", 0.0)))
    return {
        season: {event_type: sum(samples) / len(samples) for event_type, samples in groups.items()}
        for season, groups in values.items()
    }


def offensive_position_values(
    events: list[dict[str, Any]],
    position_map: dict[tuple[str, str], list[str]],
    variant: str = "all",
    include_season: int | None = None,
    excluded_team: str | None = None,
) -> list[dict[str, Any]]:
    weights = _event_type_weights(events)
    eligible = [
        event for event in events
        if event.get("is_plate_appearance")
        and (include_season is None or event["season"] == include_season)
        and (excluded_team is None or team_family(event["batting_team"]) != excluded_team)
    ]
    season_means: dict[int, float] = {}
    for season in {event["season"] for event in eligible}:
        season_rows = [event for event in eligible if event["season"] == season]
        season_means[season] = sum(weights[season][event["event_type"]] for event in season_rows) / len(season_rows)
    samples: dict[str, dict[str, Any]] = {
        position: {"PA": 0, "batting_runs_proxy": 0.0, "players": set()}
        for position in STANDARD_POSITIONS
    }
    for event in eligible:
        key = (event["canonical_id"], normalize_person_name(event.get("batter", "")))
        positions = position_map.get(key, [])
        if len(positions) != 1:
            continue
        position = positions[0]
        row = samples[position]
        row["PA"] += 1
        row["players"].add(key[1])
        row["batting_runs_proxy"] += weights[event["season"]][event["event_type"]] - season_means[event["season"]]
    raw_scale = {
        position: -100.0 * row["batting_runs_proxy"] / row["PA"] if row["PA"] else 0.0
        for position, row in samples.items()
    }
    centered = center_position_scale(raw_scale, {p: samples[p]["PA"] for p in STANDARD_POSITIONS})
    return [
        {
            "method": "offensive_scarcity_proxy",
            "variant": variant,
            "position": position,
            "PA": samples[position]["PA"],
            "players": len(samples[position]["players"]),
            "batting_runs_proxy": samples[position]["batting_runs_proxy"],
            "raw_scarcity_runs_per_100_pa": raw_scale[position],
            "centered_candidate_runs_per_25_games": centered[position],
            "official_eligible": False,
        }
        for position in STANDARD_POSITIONS
    ]


def replacement_depth_values(
    events: list[dict[str, Any]],
    position_map: dict[tuple[str, str], list[str]],
) -> list[dict[str, Any]]:
    weights = _event_type_weights(events)
    player_position: dict[tuple[str, str], dict[str, Any]] = defaultdict(lambda: {"PA": 0, "runs": 0.0})
    season_pa = defaultdict(list)
    for event in events:
        if event.get("is_plate_appearance"):
            season_pa[event["season"]].append(weights[event["season"]][event["event_type"]])
    means = {season: sum(values) / len(values) for season, values in season_pa.items()}
    for event in events:
        if not event.get("is_plate_appearance"):
            continue
        player_key = normalize_person_name(event.get("batter", ""))
        positions = position_map.get((event["canonical_id"], player_key), [])
        if len(positions) != 1:
            continue
        key = (player_key, positions[0])
        player_position[key]["PA"] += 1
        player_position[key]["runs"] += weights[event["season"]][event["event_type"]] - means[event["season"]]
    samples = {}
    for position in STANDARD_POSITIONS:
        rows = [value for (player, pos), value in player_position.items() if pos == position]
        threshold = sorted(row["PA"] for row in rows)[len(rows) // 2] if rows else 0
        lower = [row for row in rows if row["PA"] <= threshold]
        pa = sum(row["PA"] for row in lower)
        runs = sum(row["runs"] for row in lower)
        samples[position] = {"PA": pa, "runs": runs, "players": len(lower), "threshold": threshold}
    raw = {p: -100 * samples[p]["runs"] / samples[p]["PA"] if samples[p]["PA"] else 0.0 for p in STANDARD_POSITIONS}
    centered = center_position_scale(raw, {p: samples[p]["PA"] for p in STANDARD_POSITIONS})
    return [
        {
            "method": "lower_playing_time_depth_proxy",
            "variant": "all",
            "position": position,
            "PA": samples[position]["PA"],
            "players": samples[position]["players"],
            "lower_half_PA_threshold": samples[position]["threshold"],
            "centered_candidate_runs_per_25_games": centered[position],
            "official_eligible": False,
        }
        for position in STANDARD_POSITIONS
    ]


def fielding_transitions(
    events: list[dict[str, Any]],
    boxscore_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    names_by_game: dict[str, list[str]] = defaultdict(list)
    for row in boxscore_rows:
        if row["role"] == "hitting":
            names_by_game[row["canonical_id"]].append(row["player"])
    opportunities = []
    for event in events:
        batted_type = _batted_ball_type(event.get("play_text", ""))
        target = _fielding_target(event.get("play_text", ""), names_by_game[event["canonical_id"]])
        if not batted_type or not target:
            continue
        long_position, player = target
        if long_position not in POSITION_NAMES:
            continue
        opportunities.append(
            {
                "player_key": normalize_person_name(player),
                "position": POSITION_NAMES[long_position],
                "batted_type": batted_type,
                "converted": int(event["event_type"] in OUT_RESULTS),
            }
        )
    rates: dict[tuple[str, str], float] = {}
    for key in {(row["position"], row["batted_type"]) for row in opportunities}:
        values = [row["converted"] for row in opportunities if (row["position"], row["batted_type"]) == key]
        rates[key] = sum(values) / len(values)
    player_position: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in opportunities:
        player_position[(row["player_key"], row["position"])].append(
            row["converted"] - rates[(row["position"], row["batted_type"])]
        )
    players: dict[str, list[str]] = defaultdict(list)
    for player, position in player_position:
        players[player].append(position)
    pair_rows = []
    for first, second in itertools.combinations(STANDARD_POSITIONS, 2):
        switchers = [player for player, positions in players.items() if first in positions and second in positions]
        first_values = [v for player in switchers for v in player_position[(player, first)]]
        second_values = [v for player in switchers for v in player_position[(player, second)]]
        pair_rows.append(
            {
                "record_type": "within_player_transition",
                "position_a": first,
                "position_b": second,
                "players": len(switchers),
                "opportunities_a": len(first_values),
                "opportunities_b": len(second_values),
                "residual_difference_b_minus_a_per_100_opportunities": (
                    100 * ((sum(second_values) / len(second_values)) - (sum(first_values) / len(first_values)))
                    if first_values and second_values else 0.0
                ),
            }
        )
    position_rows = []
    for position in STANDARD_POSITIONS:
        values = [v for (player, pos), samples in player_position.items() if pos == position for v in samples]
        position_rows.append(
            {
                "record_type": "fielding_opportunity_sample",
                "position": position,
                "players": len({player for player, pos in player_position if pos == position}),
                "opportunities": len(values),
                "mean_position_relative_conversion_residual": sum(values) / len(values) if values else 0.0,
            }
        )
    return position_rows, pair_rows


def _ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    ranks = [0.0] * len(values)
    for rank, index in enumerate(order):
        ranks[index] = float(rank)
    return ranks


def _correlation(first: list[float], second: list[float]) -> float:
    if len(first) < 2:
        return 0.0
    a, b = _ranks(first), _ranks(second)
    ma, mb = sum(a) / len(a), sum(b) / len(b)
    numerator = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    denominator = math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))
    return numerator / denominator if denominator else 0.0


def build_positional_research(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    boxscore = read_json(snapshot / "normalized" / "player_game_boxscore.json")
    events = read_json(snapshot / "model" / "valued_events.json")
    exposure, exposure_audit, position_map = build_position_exposure(boxscore, events)

    teams = sorted({team_family(event["batting_team"]) for event in events})
    candidate_rows = offensive_position_values(events, position_map)
    for season in sorted({event["season"] for event in events}):
        candidate_rows.extend(offensive_position_values(events, position_map, f"season_{season}", include_season=season))
    for team in teams:
        candidate_rows.extend(offensive_position_values(events, position_map, f"leave_team_out:{team}", excluded_team=team))
    candidate_rows.extend(replacement_depth_values(events, position_map))
    position_samples, transitions = fielding_transitions(events, boxscore)

    full = {row["position"]: row["centered_candidate_runs_per_25_games"] for row in candidate_rows if row["method"] == "offensive_scarcity_proxy" and row["variant"] == "all"}
    validation_rows = []
    for variant in sorted({row["variant"] for row in candidate_rows if row["method"] == "offensive_scarcity_proxy" and row["variant"] != "all"}):
        comparison = {row["position"]: row["centered_candidate_runs_per_25_games"] for row in candidate_rows if row["method"] == "offensive_scarcity_proxy" and row["variant"] == variant}
        validation_rows.append(
            {
                "variant": variant,
                "spearman_vs_full": _correlation([full[p] for p in STANDARD_POSITIONS], [comparison[p] for p in STANDARD_POSITIONS]),
                "maximum_absolute_run_change": max(abs(full[p] - comparison[p]) for p in STANDARD_POSITIONS),
                "sign_agreement_positions": sum((full[p] >= 0) == (comparison[p] >= 0) for p in STANDARD_POSITIONS),
            }
        )

    transition_pass = sum(
        row["players"] >= 15 and min(row["opportunities_a"], row["opportunities_b"]) >= 200
        for row in transitions
    ) >= 7
    leave_team = [row for row in validation_rows if row["variant"].startswith("leave_team_out:")]
    season_rows = [row for row in validation_rows if row["variant"].startswith("season_")]
    season_scales = {
        row["variant"]: {
            item["position"]: item["centered_candidate_runs_per_25_games"]
            for item in candidate_rows
            if item["method"] == "offensive_scarcity_proxy" and item["variant"] == row["variant"]
        }
        for row in season_rows
    }
    season_variants = sorted(season_scales)
    direct_season_stability = (
        _correlation(
            [season_scales[season_variants[0]][p] for p in STANDARD_POSITIONS],
            [season_scales[season_variants[1]][p] for p in STANDARD_POSITIONS],
        )
        if len(season_variants) == 2 else 0.0
    )
    gates = {
        "defensible_position_innings": exposure_audit["confirmed_position_innings_coverage"] >= 0.80,
        "adequate_transition_samples": transition_pass,
        "leave_one_team_out_stability": bool(leave_team) and min(row["spearman_vs_full"] for row in leave_team) >= 0.70,
        "leave_one_season_out_stability": len(season_rows) >= 2 and direct_season_stability >= 0.70,
        "league_centered_candidates": abs(sum(full[p] * next(row["PA"] for row in candidate_rows if row["method"] == "offensive_scarcity_proxy" and row["variant"] == "all" and row["position"] == p) for p in STANDARD_POSITIONS)) < 1e-8,
        "no_double_counting_plan": True,
    }
    decision = "implement" if all(gates.values()) else "insufficient_data"
    sensitivity = {
        "snapshot_id": snapshot_id,
        "standardized_season": "25 games / 175 defensive innings",
        "cross_validation": validation_rows,
        "direct_season_to_season_spearman": direct_season_stability,
        "reliability_gates": gates,
        "decision": decision,
        "failed_gates": [name for name, passed in gates.items() if not passed],
    }

    output = project_root / "output"
    write_json(output / "positional_innings_by_player.json", exposure)
    _write_csv(output / "positional_innings_by_player.csv", exposure)
    samples = position_samples + transitions
    write_json(output / "positional_samples_and_transitions.json", samples)
    _write_csv(output / "positional_samples_and_transitions.csv", samples)
    write_json(output / "candidate_positional_scales.json", candidate_rows)
    _write_csv(output / "candidate_positional_scales.csv", candidate_rows)
    write_json(output / "positional_sensitivity_cross_validation.json", sensitivity)
    _write_csv(output / "positional_sensitivity_cross_validation.csv", validation_rows)
    write_json(output / "positional_innings_audit.json", exposure_audit)
    write_json(
        output / "positional_adjustment_recommendation.json",
        {
            "snapshot_id": snapshot_id,
            "recommendation": decision,
            "official_positional_adjustment_runs": 0.0,
            "reason": (
                "GameChanger identifies positions played but does not provide reliable innings "
                "at each position; transition samples and between-season stability also fail."
            ),
            "failed_gates": sensitivity["failed_gates"],
            "next_data_requirement": (
                "Structured starting defensive lineups and timestamped defensive substitutions "
                "sufficient to allocate outs at each position."
            ),
        },
    )

    return {
        "snapshot_id": snapshot_id,
        "decision": decision,
        "failed_gates": sensitivity["failed_gates"],
        "position_rows": len(exposure),
        "confirmed_position_innings_coverage": exposure_audit["confirmed_position_innings_coverage"],
        "team_games_with_confirmed_position_innings": exposure_audit["team_games_with_confirmed_position_innings"],
        "transition_pairs_meeting_sample_gate": sum(row["players"] >= 15 and min(row["opportunities_a"], row["opportunities_b"]) >= 200 for row in transitions),
        "official_positional_adjustment_changed": False,
    }
