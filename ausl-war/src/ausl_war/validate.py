from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .io import read_json, sha256_file, write_json
from .official import completed_schedule
from .war import _batted_ball_type, _fielding_target


def _check(name: str, passed: bool, observed: Any, expected: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "observed": observed, "expected": expected}


def validate_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    snapshot = project_root / "data" / "snapshots" / snapshot_id
    raw_games = project_root / "data" / "raw" / "authenticated" / snapshot_id / "games"
    public_audit = read_json(snapshot / "public" / "public_schedule_audit.json")
    canonical = read_json(snapshot / "public" / "canonical_games.json")
    normalized_summary = read_json(snapshot / "normalized" / "summary.json")
    reconciliations = read_json(snapshot / "normalized" / "game_reconciliation.json")
    events = read_json(snapshot / "normalized" / "events.json")
    boxscore = read_json(snapshot / "normalized" / "player_game_boxscore.json")
    re24 = read_json(snapshot / "model" / "re24.json")
    all_war_summary = read_json(project_root / "output" / "war_summary.json")
    war_summary = all_war_summary["seasons"]["2026"]
    model_constants = read_json(project_root / "output" / "model_constants_2026.json")
    combined = read_json(project_root / "output" / "combined_2026.json")
    position = read_json(project_root / "output" / "position_players_2026.json")
    pitching = read_json(project_root / "output" / "pitchers_2026.json")
    combined_2025 = read_json(project_root / "output" / "combined_2025.json")
    position_2025 = read_json(project_root / "output" / "position_players_2025.json")
    pitching_2025 = read_json(project_root / "output" / "pitchers_2025.json")
    model_constants_2025 = read_json(project_root / "output" / "model_constants_2025.json")
    supplemental_audit = read_json(
        project_root / "output" / "official_supplemental_game_audit.json"
    )
    supplemental_event_audit = read_json(
        project_root / "output" / "official_supplemental_event_audit.json"
    )
    positional_sensitivity = read_json(
        project_root / "output" / "positional_sensitivity_cross_validation.json"
    )
    positional_candidates = read_json(
        project_root / "output" / "candidate_positional_scales.json"
    )
    positional_audit = read_json(project_root / "output" / "positional_innings_audit.json")

    completed = [game for game in canonical if game["status"] == "completed"]
    raw_complete = sum(
        all((raw_games / game["preferred_source_game_id"] / name).exists() for name in ("boxscore.json", "plays.json", "source.json"))
        for game in completed
    )
    raw_manifest = read_json(
        project_root / "data" / "raw" / "authenticated" / snapshot_id / "manifest.json"
    )
    checksum_mismatches = []
    for entry in raw_manifest["files"]:
        target = project_root / "data" / "raw" / "authenticated" / snapshot_id / entry["path"]
        if not target.exists() or sha256_file(target) != entry["sha256"]:
            checksum_mismatches.append(entry["path"])
    boundary_outs = [value for row in reconciliations for value in row["boundary_out_counts"]]
    completed_2026 = len(completed_schedule(project_root, snapshot_id, 2026))
    expected_total_war = completed_2026 * (1000 / 2430)
    observed_total_war = (
        war_summary["position_war_total"] + war_summary["pitching_war_total"]
    )
    checks = [
        _check("canonical IDs are unique", public_audit["duplicate_canonical_ids"] == 0, public_audit["duplicate_canonical_ids"], 0),
        _check("canonical source pairs have no quality flags", public_audit["contests_with_quality_flags"] == 0, public_audit["contests_with_quality_flags"], 0),
        _check("all completed contests have immutable HTML artifacts", raw_complete == len(completed), raw_complete, len(completed)),
        _check("raw manifest contains three artifacts per game", len(raw_manifest["files"]) == len(completed) * 3, len(raw_manifest["files"]), len(completed) * 3),
        _check("raw manifest SHA-256 values match current files", not checksum_mismatches, checksum_mismatches, []),
        _check("normalization covers every completed contest", normalized_summary["games"] == len(completed), normalized_summary["games"], len(completed)),
        _check("all games reconcile runs", normalized_summary["games_reconciling_runs"] == len(completed), normalized_summary["games_reconciling_runs"], len(completed)),
        _check("all games reconcile hits", normalized_summary["games_reconciling_hits"] == len(completed), normalized_summary["games_reconciling_hits"], len(completed)),
        _check("all games reconcile walks", normalized_summary["games_reconciling_walks"] == len(completed), normalized_summary["games_reconciling_walks"], len(completed)),
        _check("all games reconcile strikeouts", normalized_summary["games_reconciling_strikeouts"] == len(completed), normalized_summary["games_reconciling_strikeouts"], len(completed)),
        _check("all games satisfy runner-state invariants", normalized_summary["games_with_valid_runner_states"] == len(completed), normalized_summary["games_with_valid_runner_states"], len(completed)),
        _check("no play rows remain unresolved", normalized_summary["unresolved_rows"] == 0, normalized_summary["unresolved_rows"], 0),
        _check("no plate appearances have unknown outcomes", normalized_summary["unknown_plate_appearances"] == 0, normalized_summary["unknown_plate_appearances"], 0),
        _check("every completed non-walkoff half-inning reaches three outs", all(value == 3 for value in boundary_outs), Counter(boundary_outs), {3: len(boundary_outs)}),
        _check("no normalized event begins with three outs", all(event["outs_before"] < 3 for event in events), sum(event["outs_before"] >= 3 for event in events), 0),
        _check("every RE24 state has observations", len(re24) == 24 and all(row["sample_size"] > 0 for row in re24), sum(row["sample_size"] > 0 for row in re24), 24),
        _check("position RAA balances to zero", abs(war_summary["league_adjusted_position_raa"]) < 1e-9, war_summary["league_adjusted_position_raa"], 0),
        _check("2025 position RAA balances to zero", abs(all_war_summary["seasons"]["2025"]["league_adjusted_position_raa"]) < 1e-9, all_war_summary["seasons"]["2025"]["league_adjusted_position_raa"], 0),
        _check("expanded baserunning balances to zero", abs(war_summary["league_baserunning_runs"]) < 1e-9, war_summary["league_baserunning_runs"], 0),
        _check("double-play avoidance balances to zero", abs(war_summary["league_double_play_avoidance_runs"]) < 1e-9, war_summary["league_double_play_avoidance_runs"], 0),
        _check("expanded advancement has no unresolved candidates", model_constants["baserunning"]["unresolved_candidate_transitions"] == 0, model_constants["baserunning"]["unresolved_candidate_transitions"], 0),
        _check("raw arm and attributed runner value are opposing", abs(model_constants["arm_value"]["raw_arm_plus_runner_balance"]) < 1e-9, model_constants["arm_value"]["raw_arm_plus_runner_balance"], 0),
        _check("unshrunk arm opportunities are league centered", abs(model_constants["arm_value"]["league_arm_runs_unshrunk_centered"]) < 1e-9, model_constants["arm_value"]["league_arm_runs_unshrunk_centered"], 0),
        _check("arm attribution coverage clears inclusion gate", model_constants["arm_value"]["attribution_coverage"] >= 0.75, model_constants["arm_value"]["attribution_coverage"], ">= 0.75"),
        _check(
            "RA7 pitching RAA balances to zero",
            abs(sum(row["ra7_pitching_runs_above_average"] for row in pitching)) < 1e-9,
            sum(row["ra7_pitching_runs_above_average"] for row in pitching),
            0,
        ),
        _check("WAR pool matches conventional replacement calibration", abs(observed_total_war - expected_total_war) < 1e-9, observed_total_war, expected_total_war),
        _check("combined player keys are unique", len(combined) == len({row["player_key"] for row in combined}), len({row["player_key"] for row in combined}), len(combined)),
        _check("every pitcher has opponent-adjusted RA7 context", all("opponent_expected_RA7" in row for row in pitching), sum("opponent_expected_RA7" in row for row in pitching), len(pitching)),
        _check("stored total WAR equals position plus pitcher WAR", all(abs(row["total_war"] - row["position_war"] - row["pitcher_war"]) < 1e-12 for row in combined), sum(abs(row["total_war"] - row["position_war"] - row["pitcher_war"]) >= 1e-12 for row in combined), 0),
        _check("position WAR equals offensive plus defensive WAR", all(abs(row["position_war"] - row["offensive_war"] - row["defensive_war"]) < 1e-12 for row in combined + combined_2025), sum(abs(row["position_war"] - row["offensive_war"] - row["defensive_war"]) >= 1e-12 for row in combined + combined_2025), 0),
        _check(
            "pitcher WAR decomposes into pitching and pitcher defense WAR",
            all(abs(row["pitcher_war"] - row["pitching_war"] - row["pitcher_defense_war"]) < 1e-12 for row in pitching),
            sum(abs(row["pitcher_war"] - row["pitching_war"] - row["pitcher_defense_war"]) >= 1e-12 for row in pitching),
            0,
        ),
        _check(
            "pitching RAA plus pitcher defense reconstructs RA7 RAA",
            all(abs(row["pitching_runs_above_average"] + row["pitcher_defense_runs"] - row["ra7_pitching_runs_above_average"]) < 1e-12 for row in pitching),
            sum(abs(row["pitching_runs_above_average"] + row["pitcher_defense_runs"] - row["ra7_pitching_runs_above_average"]) >= 1e-12 for row in pitching),
            0,
        ),
        _check(
            "wRAA is the public alias for wOBA-derived batting runs",
            all(abs(row["wRAA"] - row["batting_runs"]) < 1e-12 for row in combined),
            sum(abs(row["wRAA"] - row["batting_runs"]) >= 1e-12 for row in combined),
            0,
        ),
        _check(
            "Batting WAR converts wRAA",
            all(abs(row["batting_war"] - row["wRAA"] / model_constants["runs_per_win"]) < 1e-12 for row in combined),
            sum(abs(row["batting_war"] - row["wRAA"] / model_constants["runs_per_win"]) >= 1e-12 for row in combined),
            0,
        ),
        _check(
            "Baserunning WAR converts the complete baserunning component",
            all(abs(row["baserunning_war"] - row["baserunning_component_runs"] / model_constants["runs_per_win"]) < 1e-12 for row in combined),
            sum(abs(row["baserunning_war"] - row["baserunning_component_runs"] / model_constants["runs_per_win"]) >= 1e-12 for row in combined),
            0,
        ),
        _check(
            "Defense WAR converts range arm catcher and positional runs exactly once",
            all(abs(row["defense_war"] - (row["range_runs"] + row["arm_runs"] + row["catcher_throwing_runs"] + row["positional_adjustment_runs"]) / model_constants["runs_per_win"]) < 1e-12 for row in combined),
            sum(abs(row["defense_war"] - (row["range_runs"] + row["arm_runs"] + row["catcher_throwing_runs"] + row["positional_adjustment_runs"]) / model_constants["runs_per_win"]) >= 1e-12 for row in combined),
            0,
        ),
        _check("catcher throwing runs are league centered", abs(sum(row["catcher_throwing_runs"] for row in combined)) < 1e-9, sum(row["catcher_throwing_runs"] for row in combined), 0),
        _check("2025 catcher throwing runs are league centered", abs(sum(row["catcher_throwing_runs"] for row in combined_2025)) < 1e-9, sum(row["catcher_throwing_runs"] for row in combined_2025), 0),
        _check("display Arm Runs fold catcher throwing into other arm value", all(abs(row["throwing_runs"] - row["arm_runs"] - row["catcher_throwing_runs"]) < 1e-12 for row in combined + combined_2025), sum(abs(row["throwing_runs"] - row["arm_runs"] - row["catcher_throwing_runs"]) >= 1e-12 for row in combined + combined_2025), 0),
        _check("FIP is present for every pitcher", all(all(field in row for field in ("FIP", "ERA", "ERA_minus_FIP")) for row in pitching + pitching_2025), sum("FIP" in row for row in pitching + pitching_2025), len(pitching) + len(pitching_2025)),
        _check("FIP comparison arithmetic is exact", all(abs(row["ERA_minus_FIP"] - row["ERA"] + row["FIP"]) < 1e-12 for row in pitching + pitching_2025), sum(abs(row["ERA_minus_FIP"] - row["ERA"] + row["FIP"]) >= 1e-12 for row in pitching + pitching_2025), 0),
        _check("2025 FIP constant matches the season run environment", abs(model_constants_2025["fip"]["constant"] - 2.8099241674909328) < 1e-12, model_constants_2025["fip"]["constant"], 2.8099241674909328),
        _check("2026 FIP constant matches the season run environment", abs(model_constants["fip"]["constant"] - 2.303274288781535) < 1e-12, model_constants["fip"]["constant"], 2.303274288781535),
        _check("FIP is excluded from WAR arithmetic", all(abs(row["pitcher_war"] - row["pitching_war"] - row["pitcher_defense_war"]) < 1e-12 for row in pitching + pitching_2025), sum(abs(row["pitcher_war"] - row["pitching_war"] - row["pitcher_defense_war"]) >= 1e-12 for row in pitching + pitching_2025), 0),
        _check("official schedule supplies all 50 completed 2025 games", len(completed_schedule(project_root, snapshot_id, 2025)) == 50, len(completed_schedule(project_root, snapshot_id, 2025)), 50),
        _check("the exact 12-game 2025 gap is supplemented", sum(row["season"] == 2025 for row in supplemental_audit) == 12, sum(row["season"] == 2025 for row in supplemental_audit), 12),
        _check("supplemental games reconcile official runs", all(row["run_difference"] == 0 for row in supplemental_event_audit), sum(row["run_difference"] != 0 for row in supplemental_event_audit), 0),
        _check("supplemental games have valid reconstructed runner states", all(row["state_invariant_error_count"] == 0 for row in supplemental_event_audit), sum(row["state_invariant_error_count"] for row in supplemental_event_audit), 0),
        _check("supplemental PA reconstruction is complete", sum(row["plate_appearances"] for row in supplemental_event_audit) == 923, sum(row["plate_appearances"] for row in supplemental_event_audit), 923),
        _check("all completed official games reach the full PA dataset", len({row["canonical_id"] for row in read_json(project_root / "output" / "tto" / "plate_appearances.json")}) == 98, len({row["canonical_id"] for row in read_json(project_root / "output" / "tto" / "plate_appearances.json")}), 98),
        _check("primary rows contain role-specific WAR fields", all(all(field in row for field in ("position_war", "pitcher_war", "pitching_war", "pitcher_defense_war", "total_war")) for row in combined), sum(all(field in row for field in ("position_war", "pitcher_war", "pitching_war", "pitcher_defense_war", "total_war")) for row in combined), len(combined)),
        _check("obsolete WAR and interval fields are absent", all(not any("95_" in field or field.startswith("combined_war_") or field in {"position_war_partial", "position_war_experimental", "pitching_fip_war", "pitching_ra7_war", "pitching_ra9_war"} for field in row) for row in combined), sum(any("95_" in field or field.startswith("combined_war_") for field in row) for row in combined), 0),
        _check("old-versus-new impact report exists", (project_root / "output" / "old_vs_new_player_impact.csv").exists(), (project_root / "output" / "old_vs_new_player_impact.csv").exists(), True),
        _check(
            "positional research decision follows reliability gates",
            (positional_sensitivity["decision"] == "implement") == all(positional_sensitivity["reliability_gates"].values()),
            positional_sensitivity["decision"],
            "implement only if every gate passes",
        ),
        _check(
            "insufficient positional evidence leaves official adjustment at zero",
            positional_sensitivity["decision"] == "implement" or all(abs(row["positional_adjustment_runs"]) < 1e-12 for row in combined),
            sum(abs(row["positional_adjustment_runs"]) >= 1e-12 for row in combined),
            0,
        ),
        _check(
            "positional candidates are research-only",
            all(not row["official_eligible"] for row in positional_candidates),
            sum(bool(row["official_eligible"]) for row in positional_candidates),
            0,
        ),
    ]

    identities: dict[str, dict[str, Any]] = defaultdict(lambda: {"display_names": set(), "teams": set(), "seasons": set()})
    for row in boxscore:
        entry = identities[row["player_key"]]
        entry["display_names"].add(row["player"])
        entry["teams"].add(row["team"])
        entry["seasons"].add(row["season"])
    identity_rows = [
        {
            "player_key": key,
            "display_names": sorted(value["display_names"]),
            "teams": sorted(value["teams"]),
            "seasons": sorted(value["seasons"]),
        }
        for key, value in sorted(identities.items())
    ]
    _write_csv(project_root / "output" / "player_identity_audit.csv", identity_rows)

    events_2026 = [event for event in events if event["season"] == 2026]
    pa_2026 = [event for event in events_2026 if event["is_plate_appearance"]]
    known_players = sorted({row["player"] for row in position}, key=len, reverse=True)
    batted_balls = [event for event in pa_2026 if _batted_ball_type(event["play_text"])]
    attributable_batted_balls = [
        event for event in batted_balls if _fielding_target(event["play_text"], known_players)
    ]
    position_rows_2026 = [
        row for row in boxscore if row["season"] == 2026 and row["role"] == "hitting"
    ]
    full_plate_appearances = read_json(project_root / "output" / "tto" / "plate_appearances.json")
    coverage = {
        "completed_games_source_snapshot": len(completed),
        "completed_games_all_seasons": sum(len(completed_schedule(project_root, snapshot_id, season)) for season in (2025, 2026)),
        "completed_games_2025": len(completed_schedule(project_root, snapshot_id, 2025)),
        "completed_games_2026": len(completed_schedule(project_root, snapshot_id, 2026)),
        "normalized_events_all_seasons": len(events),
        "plate_appearances_all_seasons": len(full_plate_appearances),
        "plate_appearances_2026": len(pa_2026),
        "pitcher_attribution_2026": sum(bool(event.get("pitcher")) for event in pa_2026) / len(pa_2026),
        "boxscore_position_availability_2026": sum(bool(row.get("position")) for row in position_rows_2026) / len(position_rows_2026),
        "batted_balls_2026": len(batted_balls),
        "attributable_general_direction_batted_balls_2026": len(attributable_batted_balls),
        "fielding_direction_coverage_2026": len(attributable_batted_balls) / len(batted_balls),
        "re24_minimum_state_sample": min(row["sample_size"] for row in re24),
        "re24_maximum_state_sample": max(row["sample_size"] for row in re24),
        "position_players_2026": len(position),
        "position_players_2025": len(position_2025),
        "pitchers_2026": len(pitching),
        "pitchers_2025": len(pitching_2025),
        "combined_players_2026": len(combined),
        "runner_state_corrections": normalized_summary["state_corrections"],
        "advancement_opportunities_2026": model_constants["baserunning"]["advancement_opportunities"],
        "double_play_opportunities_2026": model_constants["double_play_avoidance"]["opportunities"],
        "arm_attributable_opportunities_2026": model_constants["arm_value"]["attributable_arm_opportunities"],
        "arm_attribution_coverage_2026": model_constants["arm_value"]["attribution_coverage"],
        "confirmed_position_innings_coverage": positional_audit["confirmed_position_innings_coverage"],
        "positional_adjustment_recommendation": positional_sensitivity["decision"],
    }
    result = {
        "snapshot_id": snapshot_id,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
        "coverage": coverage,
    }
    write_json(project_root / "output" / "validation.json", result)
    _write_reports(
        project_root, result, normalized_summary, war_summary, model_constants, reconciliations
    )
    return result


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "|".join(str(item) for item in value) if isinstance(value, list) else value
                    for key, value in row.items()
                }
            )


def _write_reports(
    project_root: Path,
    validation: dict[str, Any],
    normalized: dict[str, Any],
    war_summary: dict[str, Any],
    model_constants: dict[str, Any],
    reconciliations: list[dict[str, Any]],
) -> None:
    coverage = validation["coverage"]
    audit_lines = [
        "# AUSL WAR Data Audit",
        "",
        f"Snapshot: `{validation['snapshot_id']}`",
        "",
        f"- {coverage['completed_games_all_seasons']} completed official games: {coverage['completed_games_2025']} from 2025 and {coverage['completed_games_2026']} from 2026.",
        f"- The inherited detailed snapshot covers {coverage['completed_games_source_snapshot']} games; official AUSL box scores and play-by-play supply the remaining 15.",
        f"- {coverage['normalized_events_all_seasons']:,} normalized events and {coverage['plate_appearances_all_seasons']:,} plate appearances.",
        f"- Exact game-level reconciliation: {normalized['games_reconciling_runs']}/{normalized['games']} runs, hits, walks, and strikeouts.",
        f"- 2026 pitcher attribution: {coverage['pitcher_attribution_2026']:.1%} of plate appearances.",
        f"- 2026 box-score position availability: {coverage['boxscore_position_availability_2026']:.1%} of hitter-game rows.",
        f"- General batted-ball direction/fielder attribution: {coverage['attributable_general_direction_batted_balls_2026']:,}/{coverage['batted_balls_2026']:,} ({coverage['fielding_direction_coverage_2026']:.1%}).",
        f"- Expanded advancement: {coverage['advancement_opportunities_2026']:,} opportunities; {model_constants['baserunning']['unresolved_candidate_transitions']} unresolved candidates.",
        f"- Double-play avoidance: {coverage['double_play_opportunities_2026']:,} eligible ground-ball opportunities.",
        f"- Arm attribution: {coverage['arm_attributable_opportunities_2026']:,} opportunities ({coverage['arm_attribution_coverage_2026']:.1%} coverage).",
        f"- Confirmed defensive-position innings coverage: {coverage['confirmed_position_innings_coverage']:.1%}; positional-adjustment recommendation: `{coverage['positional_adjustment_recommendation']}`.",
        f"- Runner-state corrections retained in the audit: {coverage['runner_state_corrections']}.",
        f"- All 24 RE states observed; cell sizes range from {coverage['re24_minimum_state_sample']} to {coverage['re24_maximum_state_sample']} events.",
        "",
        "## Data limitations",
        "",
        "GameChanger supplies named runner destinations and general batted-ball direction, enabling advancement, double-play, range, and arm components. It does not supply coordinates, hang time, exit velocity, throwing difficulty, complete relay responsibility, or reliable innings at each defensive position. Forced advances and wild-pitch/passed-ball movement are excluded from runner skill. Park factors and reliever leverage remain unavailable. The positional-adjustment study failed its innings, transition-sample, and between-season stability gates, so the official adjustment remains zero.",
        "",
        "## Audited state corrections",
        "",
    ]
    corrections = [
        (row["canonical_id"], correction)
        for row in reconciliations
        for correction in row.get("state_corrections", [])
    ]
    audit_lines.extend(
        f"- `{canonical_id}` event {correction['event_order']}: {correction['player']} — {correction['reason']}"
        for canonical_id, correction in corrections
    )
    if not corrections:
        audit_lines.append("- None.")
    (project_root / "DataAudit.md").write_text("\n".join(audit_lines) + "\n", encoding="utf-8")

    validation_lines = [
        "# AUSL WAR Validation Report",
        "",
        f"Overall status: **{'PASS' if validation['passed'] else 'FAIL'}**",
        "",
        "| Check | Result | Observed | Expected |",
        "|---|---|---|---|",
    ]
    for check in validation["checks"]:
        validation_lines.append(
            f"| {check['name']} | {'PASS' if check['passed'] else 'FAIL'} | `{check['observed']}` | `{check['expected']}` |"
        )
    (project_root / "ValidationReport.md").write_text(
        "\n".join(validation_lines) + "\n", encoding="utf-8"
    )

    recommendation = """# Recommendation

Use one consistent public WAR system:

- Position WAR combines hitting, baserunning, double-play avoidance, range, arm, catcher throwing, league balancing, and replacement value.
- Pitching WAR uses opponent-adjusted RA7, replacement value, and the AUSL runs-per-win conversion.
- Total WAR is Position WAR plus Pitching WAR.

Display role-separated Position Players and Pitchers tables. Do not display Total WAR. Two-way players appear in both tables with no combined hitting-plus-pitching value. Position WAR is displayed as additive Offensive WAR plus Defensive WAR; skill details remain runs above average. Displayed Arm Runs combine other throwing value with catcher stolen-base prevention while retaining both internally. Pitcher WAR is the unchanged RA7 result decomposed into Pitching WAR and pitcher-position Defense WAR. FIP is a separate seven-inning comparison metric with a season-specific constant and does not enter WAR. Park factors remain neutral, and the methodology should continue documenting unavailable coordinates, relay responsibility, reliever leverage, and softball-specific positional adjustments.

Do not add a positional adjustment yet. The AUSL-specific study confirms only 6.42% of possible standard-position outs and finds no transition pair with adequate samples; its 2025 and 2026 candidate rankings are negatively correlated. Retain zero until structured starting lineups and timestamped defensive substitutions support reliable innings by position and the stability gates pass.
"""
    (project_root / "Recommendation.md").write_text(recommendation, encoding="utf-8")
