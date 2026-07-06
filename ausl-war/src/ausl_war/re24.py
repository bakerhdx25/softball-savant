from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import csv
import json
import random
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable

from .io import read_json, write_json


@dataclass(frozen=True, order=True)
class BaseOutState:
    outs: int
    bases: int

    def __post_init__(self) -> None:
        if self.outs not in (0, 1, 2):
            raise ValueError(f"outs must be 0, 1, or 2, got {self.outs}")
        if not 0 <= self.bases <= 7:
            raise ValueError(f"bases must be a three-bit value from 0 through 7, got {self.bases}")

    @property
    def on_first(self) -> bool:
        return bool(self.bases & 1)

    @property
    def on_second(self) -> bool:
        return bool(self.bases & 2)

    @property
    def on_third(self) -> bool:
        return bool(self.bases & 4)

    @property
    def label(self) -> str:
        occupied = "".join(
            str(base)
            for base, present in ((1, self.on_first), (2, self.on_second), (3, self.on_third))
            if present
        )
        return f"{self.outs} outs, {occupied or 'empty'}"


def encode_bases(on_first: bool, on_second: bool, on_third: bool) -> int:
    return int(on_first) | (int(on_second) << 1) | (int(on_third) << 2)


def all_states() -> list[BaseOutState]:
    return [BaseOutState(outs, bases) for outs in range(3) for bases in range(8)]


def annotate_runs_remaining(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add observed runs remaining before/after each normalized event.

    Input events must identify a canonical game, inning, half, event order, and
    runs scored on the event. A placed runner in extra innings is naturally
    represented in `bases_before`; no special run is added unless she scores.
    """
    grouped: dict[tuple[Any, Any, Any], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        grouped[(event["canonical_id"], event["inning"], event["half"])].append(event)

    annotated: list[dict[str, Any]] = []
    for half_events in grouped.values():
        half_events.sort(key=lambda event: event["event_order"])
        remaining_after = 0
        reverse_rows: list[dict[str, Any]] = []
        for event in reversed(half_events):
            runs = int(event.get("runs_scored", 0) or 0)
            row = {
                **event,
                "runs_remaining_after": remaining_after,
                "runs_remaining_before": remaining_after + runs,
            }
            reverse_rows.append(row)
            remaining_after += runs
        annotated.extend(reversed(reverse_rows))
    return sorted(
        annotated,
        key=lambda event: (
            event["canonical_id"],
            event["inning"],
            event["half"],
            event["event_order"],
        ),
    )


def estimate_re24(
    events: Iterable[dict[str, Any]],
    prior_pseudocount: float = 20.0,
) -> list[dict[str, Any]]:
    """Estimate raw and partial-pooling RE24 values.

    Sparse base states shrink toward the observed mean for the same out count.
    This is an empirical-Bayes posterior mean under a simple conjugate-style
    credibility model. Sample size and prior contribution remain explicit.
    """
    if prior_pseudocount < 0:
        raise ValueError("prior_pseudocount cannot be negative")
    observations: dict[BaseOutState, list[float]] = defaultdict(list)
    by_outs: dict[int, list[float]] = defaultdict(list)
    all_values: list[float] = []
    for event in events:
        state = BaseOutState(int(event["outs_before"]), int(event["bases_before"]))
        value = float(event["runs_remaining_before"])
        observations[state].append(value)
        by_outs[state.outs].append(value)
        all_values.append(value)
    if not all_values:
        raise ValueError("RE24 requires at least one event")
    global_mean = fmean(all_values)

    rows: list[dict[str, Any]] = []
    for state in all_states():
        values = observations[state]
        prior_mean = fmean(by_outs[state.outs]) if by_outs[state.outs] else global_mean
        sample_size = len(values)
        raw = fmean(values) if values else None
        smoothed = (
            (sum(values) + prior_pseudocount * prior_mean)
            / (sample_size + prior_pseudocount)
            if sample_size + prior_pseudocount > 0
            else prior_mean
        )
        rows.append(
            {
                "outs": state.outs,
                "bases": state.bases,
                "state": state.label,
                "sample_size": sample_size,
                "raw_re": raw,
                "outs_prior_re": prior_mean,
                "prior_pseudocount": prior_pseudocount,
                "smoothed_re": smoothed,
            }
        )
    return rows


def re_lookup(re_rows: Iterable[dict[str, Any]], field: str = "smoothed_re") -> dict[BaseOutState, float]:
    return {
        BaseOutState(int(row["outs"]), int(row["bases"])): float(row[field])
        for row in re_rows
    }


def add_run_values(
    events: Iterable[dict[str, Any]],
    re_rows: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    expectancy = re_lookup(re_rows)
    valued: list[dict[str, Any]] = []
    for event in events:
        before = BaseOutState(int(event["outs_before"]), int(event["bases_before"]))
        outs_after = int(event["outs_after"])
        if outs_after >= 3:
            after_re = 0.0
        else:
            after = BaseOutState(outs_after, int(event["bases_after"]))
            after_re = expectancy[after]
        run_value = float(event.get("runs_scored", 0) or 0) + after_re - expectancy[before]
        valued.append(
            {
                **event,
                "re_before": expectancy[before],
                "re_after": after_re,
                "run_value": run_value,
            }
        )
    return valued


def event_linear_weights(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    values: dict[str, list[float]] = defaultdict(list)
    for event in events:
        event_type = event.get("event_type")
        if event_type:
            values[str(event_type)].append(float(event["run_value"]))
    return [
        {
            "event_type": event_type,
            "sample_size": len(run_values),
            "linear_weight": fmean(run_values),
        }
        for event_type, run_values in sorted(values.items())
    ]


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("percentile requires observations")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def bootstrap_re24(
    events: list[dict[str, Any]],
    prior_pseudocount: float = 20.0,
    replicates: int = 500,
    seed: int = 20260704,
) -> dict[BaseOutState, tuple[float, float]]:
    by_game: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_game[str(event["canonical_id"])].append(event)
    game_ids = sorted(by_game)
    if not game_ids:
        raise ValueError("bootstrap requires games")
    generator = random.Random(seed)
    estimates: dict[BaseOutState, list[float]] = defaultdict(list)
    for _ in range(replicates):
        sample: list[dict[str, Any]] = []
        for _ in game_ids:
            sample.extend(by_game[generator.choice(game_ids)])
        for row in estimate_re24(sample, prior_pseudocount=prior_pseudocount):
            estimates[BaseOutState(row["outs"], row["bases"])].append(row["smoothed_re"])
    return {
        state: (_percentile(values, 0.025), _percentile(values, 0.975))
        for state, values in estimates.items()
    }


def build_re24_snapshot(
    project_root: Path,
    snapshot_id: str,
    prior_pseudocount: float = 20.0,
) -> dict[str, Any]:
    normalized = project_root / "data" / "snapshots" / snapshot_id / "normalized"
    events = read_json(normalized / "events.json")
    annotated = annotate_runs_remaining(events)
    rows = estimate_re24(annotated, prior_pseudocount=prior_pseudocount)
    valued = add_run_values(annotated, rows)
    weights = event_linear_weights(
        event for event in valued if event.get("is_plate_appearance")
    )

    output = project_root / "data" / "snapshots" / snapshot_id / "model"
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "re24.json", rows)
    write_json(output / "valued_events.json", valued)
    write_json(output / "event_linear_weights.json", weights)
    _write_rows(output / "re24.csv", rows)
    _write_rows(output / "event_linear_weights.csv", weights)
    summary = {
        "snapshot_id": snapshot_id,
        "events": len(valued),
        "games": len({event["canonical_id"] for event in valued}),
        "states": len(rows),
        "states_with_raw_observations": sum(row["sample_size"] > 0 for row in rows),
        "minimum_state_sample": min(row["sample_size"] for row in rows),
        "maximum_state_sample": max(row["sample_size"] for row in rows),
        "prior_pseudocount": prior_pseudocount,
        "linear_weight_event_types": len(weights),
    }
    write_json(output / "re24_summary.json", summary)
    return summary


def _write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
