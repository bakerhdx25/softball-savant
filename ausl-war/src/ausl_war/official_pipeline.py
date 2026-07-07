from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .io import read_json, write_json
from .official import (
    SEASON_IDS,
    completed_schedule,
    display_team,
    download_official_stats,
    supplemental_boxscore_rows,
    supplemental_normalized_events,
)
from .re24 import build_re24_snapshot
from .tto import (
    _download_official_game_pages,
    _download_official_schedules,
    _fit_fixed_effect_model,
    _write_csv,
    assign_series_ids,
    build_descriptive_tables,
    build_pitcher_tables,
    derive_exposures,
    validate_tto_dataset,
)
from .war import build_war_snapshot, derive_woba_constants


def new_snapshot_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _completed_games(schedules: dict[int, dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    games = []
    for season, schedule in schedules.items():
        for game in schedule["games"]:
            if game.get("recordStatus") == "Completed" and int(game["seasonId"]) == SEASON_IDS[season]:
                games.append((season, game))
    return sorted(games, key=lambda row: (row[0], row[1]["gameDateIso"], int(row[1]["gameId"])))


def _canonical_id(season: int, game: dict[str, Any]) -> str:
    return f"official-ausl-{season}-{int(game['gameId'])}"


def _score(game: dict[str, Any]) -> dict[str, int]:
    scores = {}
    for competitor in game["competitors"]:
        team = display_team(competitor["name"], 2025 if int(game["seasonId"]) == SEASON_IDS[2025] else 2026)
        competitor_id = int(competitor.get("eventTeamId", competitor.get("competitorId")))
        if competitor_id == int(game["homeTeamId"]):
            scores[team] = int(game.get("homeTeamScore") or 0)
        else:
            scores[team] = int(game.get("awayTeamScore") or 0)
    return scores


def _canonical_games(completed: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    rows = []
    for season, game in completed:
        rows.append(
            {
                "canonical_id": _canonical_id(season, game),
                "season": season,
                "start_ts": game["gameDateIso"],
                "status": "completed",
                "team_names": [display_team(row["name"], season) for row in game.get("competitors", [])],
                "score": _score(game),
                "official_game_id": int(game["gameId"]),
            }
        )
    return rows


def _audit_rows(completed: list[tuple[int, dict[str, Any]]]) -> list[dict[str, Any]]:
    return [
        {
            "season": season,
            "official_game_id": int(game["gameId"]),
            "canonical_id": _canonical_id(season, game),
        }
        for season, game in completed
    ]


def build_official_tto_study(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    events = read_json(snapshot / "normalized" / "events.json")
    valued_events = read_json(snapshot / "model" / "valued_events.json")
    linear_weights = {
        row["event_type"]: float(row["linear_weight"])
        for row in read_json(snapshot / "model" / "event_linear_weights.json")
    }
    canonical_games = read_json(snapshot / "public" / "canonical_games.json")
    schedules = _download_official_schedules(project_root, snapshot_id)
    games_by_id = {
        int(game["gameId"]): game
        for schedule in schedules.values()
        for game in schedule["games"]
        if game.get("recordStatus") == "Completed"
    }
    official_matches = {
        row["canonical_id"]: games_by_id[int(row["official_game_id"])]
        for row in canonical_games
    }
    series = assign_series_ids(official_matches)
    woba_weights = derive_woba_constants(valued_events)
    for event in events:
        event.setdefault("source_kind", "official_ausl_play_by_play")
    pa_rows = derive_exposures(
        events,
        valued_events,
        linear_weights,
        canonical_games,
        official_matches,
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
    write_json(output / "models.json", models)
    write_json(output / "validation.json", validation)
    summary = {
        "snapshot_id": snapshot_id,
        "games": len({row["canonical_id"] for row in pa_rows}),
        "plate_appearances": len(pa_rows),
        "official_completed_games": len(games_by_id),
        "validation_passed": bool(validation.get("passed")),
        "pitch_text_coverage": (
            sum(bool(row.get("pitch_text")) for row in pa_rows) / len(pa_rows)
            if pa_rows
            else None
        ),
    }
    write_json(output / "summary.json", summary)
    return summary


def validate_official_only_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    events = read_json(snapshot / "normalized" / "events.json")
    boxscore_rows = read_json(snapshot / "normalized" / "player_game_boxscore.json")
    pa = [row for row in events if row.get("is_plate_appearance")]
    expected_bf: Counter[str] = Counter()
    observed_pa: Counter[str] = Counter()
    for row in boxscore_rows:
        if row.get("role") == "pitching":
            expected_bf[row["canonical_id"]] += int(row.get("BF") or 0)
    for row in pa:
        observed_pa[row["canonical_id"]] += 1
    bf_mismatches = [
        {"canonical_id": key, "expectedBF": expected, "observedPA": observed_pa.get(key, 0)}
        for key, expected in sorted(expected_bf.items())
        if expected != observed_pa.get(key, 0)
    ]
    event_audit = read_json(project_root / "output" / "official_only_event_audit.json")
    failures = [
        row
        for row in event_audit
        if row.get("run_difference") != 0 or row.get("state_invariant_error_count")
    ]
    report = {
        "snapshot_id": snapshot_id,
        "games": len({row["canonical_id"] for row in events}),
        "events": len(events),
        "plate_appearances": len(pa),
        "pitch_text_coverage": (
            sum(bool(row.get("pitch_text")) for row in pa) / len(pa) if pa else None
        ),
        "run_or_state_validation_failures": failures,
        "boxscore_bf_mismatches": bf_mismatches,
        "passed": not failures and not bf_mismatches,
    }
    write_json(project_root / "output" / "official_only_validation.json", report)
    return report


def build_official_pipeline(project_root: Path, snapshot_id: str | None = None) -> dict[str, Any]:
    snapshot_id = snapshot_id or new_snapshot_id()
    schedules = _download_official_schedules(project_root, snapshot_id)
    completed = _completed_games(schedules)
    _download_official_game_pages(project_root, snapshot_id, [game for _, game in completed])
    stats_summary = download_official_stats(project_root, snapshot_id)

    snapshot = project_root / "data" / "snapshots" / snapshot_id
    public = snapshot / "public"
    normalized = snapshot / "normalized"
    public.mkdir(parents=True, exist_ok=True)
    normalized.mkdir(parents=True, exist_ok=True)
    canonical_games = _canonical_games(completed)
    write_json(public / "canonical_games.json", canonical_games)
    write_json(public / "summary.json", {"snapshot_id": snapshot_id, "completed_games": len(canonical_games)})

    audit_rows = _audit_rows(completed)
    events, event_audit = supplemental_normalized_events(project_root, snapshot_id, audit_rows)
    boxscore_rows, boxscore_audit = supplemental_boxscore_rows(project_root, snapshot_id, [])
    write_json(normalized / "events.json", events)
    write_json(normalized / "player_game_boxscore.json", boxscore_rows)
    write_json(project_root / "output" / "official_only_event_audit.json", event_audit)
    write_json(project_root / "output" / "official_only_boxscore_audit.json", boxscore_audit)

    re24_summary = build_re24_snapshot(project_root, snapshot_id)
    tto_summary = build_official_tto_study(project_root, snapshot_id)
    war_summary = build_war_snapshot(project_root, snapshot_id)
    validation = validate_official_only_snapshot(project_root, snapshot_id)

    summary = {
        "snapshot_id": snapshot_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "official_ausl_public",
        "completed_games": len(completed),
        "official_stats": stats_summary,
        "re24": re24_summary,
        "tto": tto_summary,
        "war": war_summary,
        "validation": validation,
    }
    write_json(project_root / "output" / "official_pipeline_summary.json", summary)
    return summary
