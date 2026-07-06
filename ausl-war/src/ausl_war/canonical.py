from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from .io import read_json, write_json


def normalize_team_name(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return "".join(token for token in tokens if token != "ausl")


def canonical_contest_key(
    season: int,
    team_ids: Iterable[str],
    start_ts: str,
    discriminator: str = "",
) -> str:
    teams = "+".join(sorted(team_ids))
    raw = f"{season}|{teams}|{start_ts}|{discriminator}"
    return f"ausl-{season}-{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


def _scores_are_consistent(rows: list[dict[str, Any]]) -> bool:
    scored = [row.get("score") for row in rows if isinstance(row.get("score"), dict)]
    if len(scored) < 2:
        return True
    first = scored[0]
    return all(
        score.get("team") == first.get("opponent_team")
        and score.get("opponent_team") == first.get("team")
        for score in scored[1:]
    )


def _inverse_scores(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_score = left.get("score")
    right_score = right.get("score")
    if not isinstance(left_score, dict) or not isinstance(right_score, dict):
        return False
    return (
        left_score.get("team") == right_score.get("opponent_team")
        and left_score.get("opponent_team") == right_score.get("team")
    )


def split_same_time_contests(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Split doubleheaders that GameChanger scheduled at the same timestamp.

    Each team uses a different source UUID, so completed collisions are paired
    using complementary home/away designations and inverse final scores. If the
    evidence cannot produce an unambiguous pairing, the rows remain together
    and receive quality flags instead of being silently guessed apart.
    """
    if len(rows) <= 2:
        return [rows]
    homes = sorted(
        (row for row in rows if row.get("home_away") == "home"),
        key=lambda row: row["id"],
    )
    aways = sorted(
        (row for row in rows if row.get("home_away") == "away"),
        key=lambda row: row["id"],
    )
    if len(homes) != len(aways):
        return [rows]

    candidates = {
        home["id"]: [away for away in aways if _inverse_scores(home, away)]
        for home in homes
    }
    if any(len(matches) != 1 for matches in candidates.values()):
        return [rows]
    selected_ids = [matches[0]["id"] for matches in candidates.values()]
    if len(selected_ids) != len(set(selected_ids)):
        return [rows]
    return [[home, candidates[home["id"]][0]] for home in homes]


def canonicalize_snapshot(snapshot: Path, output_dir: Path) -> dict[str, Any]:
    teams = read_json(snapshot / "teams.json")
    by_name: dict[tuple[int, str], dict[str, Any]] = {}
    for team in teams:
        by_name[(int(team["season"]), normalize_team_name(team["name"]))] = team

    source_rows: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for owner in teams:
        season = int(owner["season"])
        games = read_json(snapshot / "games" / str(season) / f"{owner['id']}.json")
        for game in games:
            opponent_name = game.get("opponent_team", {}).get("name", "")
            opponent = by_name.get((season, normalize_team_name(opponent_name)))
            if opponent is None:
                unresolved.append(
                    {
                        "season": season,
                        "source_team_id": owner["id"],
                        "source_game_id": game.get("id"),
                        "opponent_name": opponent_name,
                    }
                )
                continue
            team_ids = sorted([owner["id"], opponent["id"]])
            base_key = canonical_contest_key(season, team_ids, game["start_ts"])
            enriched = {
                **game,
                "season": season,
                "source_team_id": owner["id"],
                "source_team_name": owner["name"],
                "opponent_team_id": opponent["id"],
                "base_canonical_id": base_key,
            }
            source_rows.append(enriched)

    base_grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in source_rows:
        base_grouped[row["base_canonical_id"]].append(row)

    grouped: dict[str, list[dict[str, Any]]] = {}
    for rows in base_grouped.values():
        contests = split_same_time_contests(rows)
        for contest in contests:
            first = contest[0]
            discriminator = ""
            if len(contests) > 1:
                discriminator = "+".join(sorted(row["id"] for row in contest))
            canonical_id = canonical_contest_key(
                first["season"],
                [first["source_team_id"], first["opponent_team_id"]],
                first["start_ts"],
                discriminator,
            )
            grouped[canonical_id] = contest

    canonical_games: list[dict[str, Any]] = []
    crosswalk: list[dict[str, Any]] = []
    for canonical_id, rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: (row["source_team_id"], row["id"]))
        owners = sorted({row["source_team_id"] for row in rows})
        team_ids = sorted({row["source_team_id"] for row in rows} | {row["opponent_team_id"] for row in rows})
        flags: list[str] = []
        if len(rows) != 2:
            flags.append(f"source_row_count_{len(rows)}")
        if len(owners) != 2:
            flags.append(f"source_owner_count_{len(owners)}")
        if len(team_ids) != 2:
            flags.append(f"team_count_{len(team_ids)}")
        if len({row.get("start_ts") for row in rows}) != 1:
            flags.append("start_time_mismatch")
        if len({row.get("game_status") for row in rows}) != 1:
            flags.append("status_mismatch")
        home_away = {row.get("home_away") for row in rows}
        if len(rows) == 2 and home_away != {"home", "away"}:
            flags.append("home_away_mismatch")
        if not _scores_are_consistent(rows):
            flags.append("score_mismatch")

        preferred = next((row for row in rows if row.get("home_away") == "home"), rows[0])
        canonical_games.append(
            {
                "canonical_id": canonical_id,
                "season": preferred["season"],
                "team_ids": team_ids,
                "team_names": sorted({row["source_team_name"] for row in rows}),
                "start_ts": preferred.get("start_ts"),
                "end_ts": preferred.get("end_ts"),
                "timezone": preferred.get("timezone"),
                "status": preferred.get("game_status"),
                "preferred_source_game_id": preferred.get("id"),
                "source_game_ids": sorted(row["id"] for row in rows),
                "score": preferred.get("score"),
                "quality_flags": flags,
            }
        )
        for row in rows:
            crosswalk.append(
                {
                    "canonical_id": canonical_id,
                    "season": row["season"],
                    "source_team_id": row["source_team_id"],
                    "source_team_name": row["source_team_name"],
                    "source_game_id": row["id"],
                    "home_away": row.get("home_away"),
                    "status": row.get("game_status"),
                    "start_ts": row.get("start_ts"),
                }
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "canonical_games.json", canonical_games)
    write_json(output_dir / "game_crosswalk.json", crosswalk)
    write_json(output_dir / "unresolved_opponents.json", unresolved)
    _write_csv(output_dir / "canonical_games.csv", canonical_games)
    _write_csv(output_dir / "game_crosswalk.csv", crosswalk)

    completed = [game for game in canonical_games if game["status"] == "completed"]
    audit = {
        "snapshot_id": snapshot.name,
        "source_schedule_rows": len(source_rows) + len(unresolved),
        "resolved_source_rows": len(source_rows),
        "unresolved_source_rows": len(unresolved),
        "canonical_contests": len(canonical_games),
        "completed_canonical_contests": len(completed),
        "duplicate_canonical_ids": len(canonical_games) - len({g["canonical_id"] for g in canonical_games}),
        "contests_with_quality_flags": sum(bool(game["quality_flags"]) for game in canonical_games),
        "quality_flag_counts": _flag_counts(canonical_games),
    }
    write_json(output_dir / "public_schedule_audit.json", audit)
    return audit


def _flag_counts(games: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for game in games:
        for flag in game["quality_flags"]:
            counts[flag] += 1
    return dict(sorted(counts.items()))


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: "|".join(value) if isinstance(value, list) else value
                    for key, value in row.items()
                }
            )
