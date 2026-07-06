from __future__ import annotations

import csv
import json
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .io import read_json, write_json
from .re24 import encode_bases


BASE_NUMBER = {"1st": 1, "2nd": 2, "3rd": 3, "home": 4}


def normalize_person_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return "".join(re.findall(r"[a-z0-9]+", text.lower()))


def parse_position(info: str) -> str | None:
    matches = re.findall(r"\(([^)]+)\)", info or "")
    for value in matches:
        if value not in {"W", "L", "S"}:
            return value
    return None


def parse_innings(value: str) -> float:
    text = str(value or "0")
    if "." not in text:
        return float(int(text or 0))
    whole, thirds = text.split(".", 1)
    if thirds not in {"0", "1", "2"}:
        raise ValueError(f"Invalid softball innings value: {value}")
    return int(whole) + int(thirds) / 3


def classify_plate_appearance(text: str) -> str:
    low = text.lower()
    if "inside the park home run" in low or re.search(r"\bhomers?\b", low):
        return "home_run"
    if "double play" in low:
        return "double_play"
    if re.search(r"\btriples?\b", low):
        return "triple"
    if re.search(r"\bdoubles?\b", low):
        return "double"
    if re.search(r"\bsingles?\b", low):
        return "single"
    if "is intentionally walked" in low:
        return "intentional_walk"
    if re.search(r"\bwalks?\b", low):
        return "walk"
    if "is hit by pitch" in low:
        return "hit_by_pitch"
    if "catcher's interference" in low:
        return "catcher_interference"
    if "reaches on dropped 3rd strike" in low:
        return "dropped_third_reached"
    if "out at first on dropped 3rd strike" in low:
        return "dropped_third_out"
    if "strikes out" in low:
        return "strikeout"
    if "reaches on an error" in low:
        return "reached_on_error"
    if "fielder's choice" in low:
        return "fielders_choice"
    if "sacrifice fly" in low:
        return "sacrifice_fly"
    if "sacrific" in low:
        return "sacrifice_bunt"
    if "infield fly" in low:
        return "infield_fly"
    if "batter interference" in low:
        return "batter_interference"
    if re.search(r"\b(?:grounds|flies|pops|lines|bunts) out\b", low):
        return "out"
    return "unknown"


def batter_destination(event_type: str) -> int | None:
    return {
        "single": 1,
        "walk": 1,
        "intentional_walk": 1,
        "hit_by_pitch": 1,
        "catcher_interference": 1,
        "dropped_third_reached": 1,
        "reached_on_error": 1,
        "fielders_choice": 1,
        "double": 2,
        "triple": 3,
        "home_run": 4,
    }.get(event_type)


def outs_on_plate_appearance(event_type: str, text: str) -> int:
    low = text.lower()
    if "triple play" in low:
        return 3
    if "double play" in low:
        return 2
    if event_type in {
        "strikeout",
        "dropped_third_out",
        "sacrifice_fly",
        "sacrifice_bunt",
        "infield_fly",
        "batter_interference",
        "out",
    }:
        return 1
    return 0


@dataclass
class RunnerState:
    runners: dict[int, str]

    @classmethod
    def empty(cls) -> "RunnerState":
        return cls({})

    def mask(self) -> int:
        return encode_bases(1 in self.runners, 2 in self.runners, 3 in self.runners)

    def snapshot(self) -> dict[str, str]:
        return {str(base): runner for base, runner in sorted(self.runners.items())}

    def invariant_errors(self) -> list[str]:
        errors = []
        invalid_bases = sorted(base for base in self.runners if base not in (1, 2, 3))
        if invalid_bases:
            errors.append(f"invalid bases: {invalid_bases}")
        named = [
            normalize_person_name(runner)
            for runner in self.runners.values()
            if runner != "__placed_runner__"
        ]
        duplicates = sorted(name for name, count in Counter(named).items() if count > 1)
        if duplicates:
            errors.append(f"duplicate runners: {duplicates}")
        if self.mask() != encode_bases(
            1 in self.runners, 2 in self.runners, 3 in self.runners
        ):
            errors.append("base mask disagrees with named runners")
        return errors

    def remove(self, name: str) -> int | None:
        key = normalize_person_name(name)
        for base, runner in list(self.runners.items()):
            if normalize_person_name(runner) == key or runner == "__placed_runner__":
                del self.runners[base]
                return base
        return None

    def place(self, base: int, name: str) -> None:
        if base in (1, 2, 3):
            self.remove(name)
            self.runners[base] = name


def _known_name_at_start(clause: str, known_names: list[str]) -> str | None:
    normalized_clause = clause.strip().lower()
    for name in known_names:
        if normalized_clause.startswith(name.lower()):
            return name
    return None


def _destination(clause: str) -> int | None:
    match = re.search(r"(?:to|at) (1st|2nd|3rd|home)\b", clause, re.I)
    return BASE_NUMBER.get(match.group(1).lower()) if match else None


def _make_room_for_runner(
    state: RunnerState, destination: int, incoming_runner: str
) -> tuple[int, list[dict[str, Any]]]:
    occupant = state.runners.get(destination)
    if not occupant or normalize_person_name(occupant) == normalize_person_name(incoming_runner):
        return 0, []
    del state.runners[destination]
    if destination == 3:
        return 0, [
            {
                "runner": occupant,
                "action": "state_correction",
                "from_base": 3,
                "to_base": None,
                "reason": "unnamed runner displaced from third; no run inferred",
            }
        ]
    runs, actions = _make_room_for_runner(state, destination + 1, occupant)
    state.runners[destination + 1] = occupant
    actions.append(
        {
            "runner": occupant,
            "action": "forced",
            "from_base": destination,
            "to_base": destination + 1,
        }
    )
    return runs, actions


def apply_runner_clauses(
    state: RunnerState,
    text: str,
    known_names: list[str],
) -> tuple[int, int, list[dict[str, Any]]]:
    """Apply named runner actions, clearing scores/outs before base advances."""
    runs = 0
    outs = 0
    actions: list[dict[str, Any]] = []
    clauses = [part.strip() for part in re.split(r",\s*", text.replace("\xa0", " "))]
    parsed: list[tuple[int, str, str, int | None, str]] = []
    for order, clause in enumerate(clauses):
        runner = _known_name_at_start(clause, known_names)
        if not runner:
            continue
        low = clause.lower()
        destination = _destination(clause)
        if "did not score" in low:
            kind = "remain_third"
        elif (
            "caught stealing" in low
            or "out advancing" in low
            or " out at " in f" {low} "
            or "picked off" in low
        ):
            kind = "out"
        elif re.search(r"\bscores?\b", low) or destination == 4:
            kind = "score"
        elif (
            "remains at" in low
            or "held up at" in low
            or "advances to" in low
            or re.search(r"\bsteals?\b", low)
        ) and destination:
            kind = "remain" if "remains at" in low or "held up at" in low else "advance"
        else:
            continue
        parsed.append((order, runner, low, destination, kind))

    terminal_runners = {
        normalize_person_name(runner)
        for _, runner, _, _, kind in parsed
        if kind in {"score", "out"}
    }
    for _, runner, low, destination, kind in sorted(
        parsed, key=lambda item: (0 if item[4] in {"score", "out"} else 1, item[0])
    ):
        if kind not in {"score", "out"} and normalize_person_name(runner) in terminal_runners:
            continue
        source = next(
            (base for base, value in state.runners.items() if normalize_person_name(value) == normalize_person_name(runner)),
            None,
        )
        if kind == "remain_third":
            state.place(3, runner)
            actions.append({"runner": runner, "action": "remain", "from_base": source, "to_base": 3})
        elif kind == "out":
            state.remove(runner)
            outs += 1
            actions.append({"runner": runner, "action": "out", "from_base": source, "to_base": destination})
        elif kind == "score":
            state.remove(runner)
            runs += 1
            actions.append({"runner": runner, "action": "score", "from_base": source, "to_base": 4})
        elif destination:
            forced_runs, forced_actions = _make_room_for_runner(
                state, destination, runner
            )
            runs += forced_runs
            actions.extend(forced_actions)
            state.place(destination, runner)
            actions.append(
                {
                    "runner": runner,
                    "action": kind,
                    "from_base": source,
                    "to_base": destination,
                }
            )
    return runs, outs, actions


def _force_walk(state: RunnerState) -> int:
    runs = 0
    if 1 in state.runners:
        if 2 in state.runners:
            if 3 in state.runners:
                del state.runners[3]
                runs += 1
            state.runners[3] = state.runners.pop(2)
        state.runners[2] = state.runners.pop(1)
    return runs


def _advance_for_batter(
    state: RunnerState, destination: int
) -> tuple[int, list[dict[str, Any]]]:
    """Apply only the minimum advancement required to make room for a batter."""
    runs = 0
    actions: list[dict[str, Any]] = []

    def move_runner(source: int, target: int) -> None:
        nonlocal runs
        runner = state.runners.pop(source)
        if target >= 4:
            actions.append(
                {
                    "runner": runner,
                    "action": "state_correction",
                    "from_base": source,
                    "to_base": None,
                    "reason": "unnamed runner would cross home; no run inferred",
                }
            )
            return
        if target in state.runners:
            move_runner(target, target + 1)
        state.runners[target] = runner
        actions.append(
            {"runner": runner, "action": "forced", "from_base": source, "to_base": target}
        )

    for source in range(min(destination, 3), 0, -1):
        if source in state.runners:
            move_runner(source, source + destination)
    return runs, actions


def _classify_runner_event(pitch_text: str) -> str | None:
    low = pitch_text.lower()
    labels = []
    if "caught stealing" in low:
        labels.append("caught_stealing")
    if re.search(r"\bsteals?\b", low):
        labels.append("stolen_base")
    if "wild pitch" in low:
        labels.append("wild_pitch")
    if "passed ball" in low:
        labels.append("passed_ball")
    if "leaving base early" in low or "picked off" in low:
        labels.append("runner_out")
    if not labels and (" scores on error" in low or " advances to " in low):
        labels.append("runner_advance")
    return "+".join(labels) if labels else None


def _extract_pitcher(text: str, known_pitchers: list[str]) -> str | None:
    low = text.lower()
    for pitcher in sorted(known_pitchers, key=len, reverse=True):
        if f"{pitcher.lower()} pitching" in low or f"{pitcher.lower()} in for pitcher" in low:
            return pitcher
    return None


def apply_pinch_runner_substitution(
    state: RunnerState,
    pitch_text: str,
    known_names: list[str],
) -> tuple[str, str, int] | None:
    low = pitch_text.lower()
    for new_runner in known_names:
        marker = f"pinch runner {new_runner.lower()} in for"
        marker_index = low.find(marker)
        if marker_index < 0:
            continue
        remainder = low[marker_index + len(marker):]
        for old_runner in known_names:
            if old_runner == new_runner or old_runner.lower() not in remainder:
                continue
            old_key = normalize_person_name(old_runner)
            for base, existing in list(state.runners.items()):
                if normalize_person_name(existing) == old_key:
                    state.runners[base] = new_runner
                    return new_runner, old_runner, base
    return None


def normalize_game(
    canonical_id: str,
    source_game_id: str,
    season: int,
    boxscore: dict[str, Any],
    play_rows: list[dict[str, str]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    hitters = boxscore.get("hitting", [])
    known_names = sorted({row["Player"] for row in hitters}, key=len, reverse=True)
    team_by_name = {normalize_person_name(row["Player"]): row["teamName"] for row in hitters}
    known_pitchers = sorted({row["Player"] for row in boxscore.get("pitching", [])}, key=len, reverse=True)
    pitchers_by_team: dict[str, list[str]] = {}
    for pitcher_row in boxscore.get("pitching", []):
        pitchers_by_team.setdefault(pitcher_row["teamName"], []).append(pitcher_row["Player"])
    away = boxscore.get("awayTeamName")
    home = boxscore.get("homeTeamName")

    events: list[dict[str, Any]] = []
    state = RunnerState.empty()
    outs = 0
    half_index = -1
    current_team: str | None = None
    current_pitcher_by_team = {
        team: pitchers[0] for team, pitchers in pitchers_by_team.items() if pitchers
    }
    unresolved_rows = 0
    state_invariant_errors: list[dict[str, Any]] = []
    boundary_out_counts: list[int] = []
    pa_count = 0

    for display_index, row in enumerate(reversed(play_rows)):
        play_text = (row.get("play") or "").replace("\xa0", " ").strip()
        pitch_text = (row.get("pitch") or "").replace("\xa0", " ").strip()
        batter = _known_name_at_start(play_text, known_names)
        batting_team = team_by_name.get(normalize_person_name(batter or ""))
        special = play_text.lower().startswith("half-inning ended") or not batter
        if batting_team and batting_team != current_team:
            if current_team is not None:
                boundary_out_counts.append(outs)
            half_index += 1
            current_team = batting_team
            state = RunnerState.empty()
            outs = 0
            # AUSL uses the international tiebreaker in extra innings. Keep an
            # anonymous runner on second until the first explicit clause names her.
            if half_index // 2 + 1 >= 8:
                state.runners[2] = "__placed_runner__"
        elif current_team is None and batting_team:
            half_index = 0
            current_team = batting_team

        if not current_team:
            unresolved_rows += 1
            continue

        inning = half_index // 2 + 1
        half = "top" if half_index % 2 == 0 else "bottom"
        defense = home if current_team == away else away
        current_pitcher = current_pitcher_by_team.get(defense)
        pitcher_change = _extract_pitcher(pitch_text, known_pitchers)
        if pitcher_change:
            current_pitcher = pitcher_change
            current_pitcher_by_team[defense] = pitcher_change
        explicit_pitcher = _extract_pitcher(play_text, known_pitchers)
        if explicit_pitcher:
            current_pitcher = explicit_pitcher
            current_pitcher_by_team[defense] = explicit_pitcher
        apply_pinch_runner_substitution(state, pitch_text, known_names)

        runner_text = pitch_text if pitch_text else (play_text if not batter else "")
        runner_type = _classify_runner_event(runner_text)
        if runner_type:
            before_mask = state.mask()
            runners_before = state.snapshot()
            before_outs = outs
            runs, runner_outs, actions = apply_runner_clauses(state, runner_text, known_names)
            outs = min(3, outs + runner_outs)
            for error in state.invariant_errors():
                state_invariant_errors.append({"display_row_index": display_index, "error": error})
            events.append(
                {
                    "canonical_id": canonical_id,
                    "source_game_id": source_game_id,
                    "season": season,
                    "inning": inning,
                    "half": half,
                    "event_order": len(events) + 1,
                    "display_row_index": display_index,
                    "event_type": runner_type,
                    "is_plate_appearance": False,
                    "batting_team": current_team,
                    "fielding_team": defense,
                    "batter": batter,
                    "pitcher": current_pitcher,
                    "outs_before": before_outs,
                    "bases_before": before_mask,
                    "runners_before": runners_before,
                    "outs_after": outs,
                    "bases_after": state.mask(),
                    "runners_after": state.snapshot(),
                    "runs_scored": runs,
                    "runner_actions": actions,
                    "pitch_text": pitch_text,
                    "play_text": "",
                }
            )

        if play_text.lower().startswith("half-inning ended"):
            if runner_type and outs >= 3:
                # GameChanger adds a display-only marker after the caught
                # stealing already represented in this same row.
                continue
            before_outs = outs
            runners_before = state.snapshot()
            outs = 3
            events.append(
                {
                    "canonical_id": canonical_id,
                    "source_game_id": source_game_id,
                    "season": season,
                    "inning": inning,
                    "half": half,
                    "event_order": len(events) + 1,
                    "display_row_index": display_index,
                    "event_type": "runner_out",
                    "is_plate_appearance": False,
                    "batting_team": current_team,
                    "fielding_team": defense,
                    "batter": None,
                    "pitcher": current_pitcher,
                    "outs_before": before_outs,
                    "bases_before": state.mask(),
                    "runners_before": runners_before,
                    "outs_after": outs,
                    "bases_after": state.mask(),
                    "runners_after": state.snapshot(),
                    "runs_scored": 0,
                    "runner_actions": [],
                    "pitch_text": pitch_text,
                    "play_text": play_text,
                }
            )
            continue
        if special and not batter:
            # A standalone wild-pitch row was already represented above.
            if not runner_type:
                unresolved_rows += 1
            continue

        event_type = classify_plate_appearance(play_text)
        before_mask = state.mask()
        runners_before = state.snapshot()
        before_outs = outs
        runs, runner_outs, actions = apply_runner_clauses(state, play_text, known_names)
        forced_runs = 0
        if event_type in {"walk", "intentional_walk", "hit_by_pitch", "catcher_interference"}:
            forced_runs = _force_walk(state)
        destination = batter_destination(event_type)
        explicit_batter_action = next(
            (
                action
                for action in actions
                if normalize_person_name(action["runner"]) == normalize_person_name(batter)
            ),
            None,
        )
        if destination == 4 and not explicit_batter_action:
            # GameChanger lists other runners scoring but generally does not add
            # a redundant "batter scores" clause on a home run.
            forced_runs, forced_actions = _advance_for_batter(state, destination)
            runs += forced_runs
            actions.extend(forced_actions)
            state.remove(batter)
            runs += 1
        elif destination and not explicit_batter_action:
            forced_runs, forced_actions = _advance_for_batter(state, destination)
            runs += forced_runs
            actions.extend(forced_actions)
            state.place(destination, batter)
        pa_outs = outs_on_plate_appearance(event_type, play_text)
        # `double play`/`triple play` labels describe total outs on the play;
        # their explicit runner clause is not an additional out. Fielder's
        # choices have pa_outs=0, so their named runner out still counts.
        outs = min(3, outs + max(runner_outs, pa_outs))
        for error in state.invariant_errors():
            state_invariant_errors.append({"display_row_index": display_index, "error": error})
        events.append(
            {
                "canonical_id": canonical_id,
                "source_game_id": source_game_id,
                "season": season,
                "inning": inning,
                "half": half,
                "event_order": len(events) + 1,
                "display_row_index": display_index,
                "event_type": event_type,
                "is_plate_appearance": True,
                "batting_team": current_team,
                "fielding_team": defense,
                "batter": batter,
                "pitcher": current_pitcher,
                "outs_before": before_outs,
                "bases_before": before_mask,
                "runners_before": runners_before,
                "outs_after": outs,
                "bases_after": state.mask(),
                "runners_after": state.snapshot(),
                "runs_scored": runs + forced_runs,
                "runner_actions": actions,
                "pitch_text": pitch_text,
                "play_text": play_text,
            }
        )
        pa_count += 1

    expected_runs = sum(int(row.get("R", 0) or 0) for row in hitters)
    observed_runs = sum(int(event["runs_scored"]) for event in events)
    expected_hits = sum(int(row.get("H", 0) or 0) for row in hitters)
    observed_hits = sum(
        event["event_type"] in {"single", "double", "triple", "home_run"}
        for event in events
        if event["is_plate_appearance"]
    )
    expected_walks = sum(int(row.get("BB", 0) or 0) for row in hitters)
    observed_walks = sum(
        event["event_type"] in {"walk", "intentional_walk"}
        for event in events
        if event["is_plate_appearance"]
    )
    expected_strikeouts = sum(int(row.get("SO", 0) or 0) for row in hitters)
    observed_strikeouts = sum(
        event["event_type"] in {"strikeout", "dropped_third_out", "dropped_third_reached"}
        for event in events
        if event["is_plate_appearance"]
    )
    audit = {
        "canonical_id": canonical_id,
        "source_game_id": source_game_id,
        "season": season,
        "display_rows": len(play_rows),
        "normalized_events": len(events),
        "plate_appearances": pa_count,
        "half_innings": half_index + 1,
        "first_batting_team": events[0]["batting_team"] if events else None,
        "away_team": away,
        "unresolved_rows": unresolved_rows,
        "unknown_plate_appearances": sum(
            event["event_type"] == "unknown" for event in events if event["is_plate_appearance"]
        ),
        "boundary_out_counts": boundary_out_counts,
        "expected_runs": expected_runs,
        "observed_runs": observed_runs,
        "run_difference": observed_runs - expected_runs,
        "expected_hits": expected_hits,
        "observed_hits": observed_hits,
        "hit_difference": observed_hits - expected_hits,
        "expected_walks": expected_walks,
        "observed_walks": observed_walks,
        "walk_difference": observed_walks - expected_walks,
        "expected_strikeouts": expected_strikeouts,
        "observed_strikeouts": observed_strikeouts,
        "strikeout_difference": observed_strikeouts - expected_strikeouts,
        "state_invariant_errors": state_invariant_errors,
        "state_invariant_error_count": len(state_invariant_errors),
        "state_corrections": [
            {
                "canonical_id": canonical_id,
                "event_order": event["event_order"],
                "player": action["runner"],
                "reason": action.get("reason"),
                "play_text": event["play_text"],
            }
            for event in events
            for action in event.get("runner_actions", [])
            if action.get("action") == "state_correction"
        ],
    }
    return events, audit


def normalized_boxscore_rows(
    canonical_id: str,
    source_game_id: str,
    season: int,
    boxscore: dict[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for role in ("hitting", "pitching"):
        for row in boxscore.get(role, []):
            result = {
                "canonical_id": canonical_id,
                "source_game_id": source_game_id,
                "season": season,
                "role": role,
                "team": row.get("teamName"),
                "player": row.get("Player"),
                "player_key": normalize_person_name(row.get("Player", "")),
                "jersey_number": row.get("jerseyNumber"),
                "position": parse_position(row.get("Info", "")),
            }
            for key, value in row.items():
                if key not in {"teamName", "Player", "Info", "jerseyNumber"}:
                    result[key] = value
            if role == "pitching":
                result["innings_decimal"] = parse_innings(row.get("IP", "0"))
            rows.append(result)
    return rows


def normalize_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    raw_root = project_root / "data" / "raw" / "authenticated" / snapshot_id / "games"
    canonical_games = read_json(
        project_root / "data" / "snapshots" / snapshot_id / "public" / "canonical_games.json"
    )
    completed_by_source = {
        game["preferred_source_game_id"]: game for game in canonical_games if game["status"] == "completed"
    }
    all_events: list[dict[str, Any]] = []
    audits: list[dict[str, Any]] = []
    boxscore_rows: list[dict[str, Any]] = []
    for source_game_id, game in sorted(completed_by_source.items()):
        game_root = raw_root / source_game_id
        source = read_json(game_root / "source.json")
        boxscore = read_json(game_root / "boxscore.json")
        plays = read_json(game_root / "plays.json").get("plays", [])
        events, audit = normalize_game(
            game["canonical_id"], source_game_id, int(game["season"]), boxscore, plays
        )
        all_events.extend(events)
        audits.append(audit)
        boxscore_rows.extend(
            normalized_boxscore_rows(
                game["canonical_id"], source_game_id, int(game["season"]), boxscore
            )
        )

    output = project_root / "data" / "snapshots" / snapshot_id / "normalized"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "events.json", all_events)
    write_json(output / "game_reconciliation.json", audits)
    write_json(output / "player_game_boxscore.json", boxscore_rows)
    _write_csv(output / "events.csv", all_events)
    _write_csv(output / "game_reconciliation.csv", audits)
    _write_csv(output / "player_game_boxscore.csv", boxscore_rows)
    summary = {
        "snapshot_id": snapshot_id,
        "games": len(audits),
        "normalized_events": len(all_events),
        "plate_appearances": sum(event["is_plate_appearance"] for event in all_events),
        "unknown_plate_appearances": sum(audit["unknown_plate_appearances"] for audit in audits),
        "unresolved_rows": sum(audit["unresolved_rows"] for audit in audits),
        "games_reconciling_runs": sum(audit["run_difference"] == 0 for audit in audits),
        "games_reconciling_hits": sum(audit["hit_difference"] == 0 for audit in audits),
        "games_reconciling_walks": sum(audit["walk_difference"] == 0 for audit in audits),
        "games_reconciling_strikeouts": sum(
            audit["strikeout_difference"] == 0 for audit in audits
        ),
        "games_with_valid_runner_states": sum(
            audit["state_invariant_error_count"] == 0 for audit in audits
        ),
        "state_corrections": sum(len(audit["state_corrections"]) for audit in audits),
        "event_type_counts": dict(
            sorted(Counter(event["event_type"] for event in all_events).items())
        ),
    }
    write_json(output / "summary.json", summary)
    return summary


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
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
