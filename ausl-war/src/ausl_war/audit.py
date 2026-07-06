from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator

from .io import read_json, write_json


SEMANTIC_TERMS = {
    "batter_identity": ("batter", "hitter"),
    "pitcher_identity": ("pitcher",),
    "runner_identity": ("runner", "baserunner"),
    "fielder_identity": ("fielder", "fielding", "putout", "assist"),
    "base_occupancy": ("base", "first", "second", "third", "on_1", "on_2", "on_3"),
    "outs": ("out",),
    "pitching_change": ("pitching_change", "pitcher_change", "substitution"),
    "inherited_runner": ("inherited",),
    "batted_ball": ("batted", "hit_type", "direction", "trajectory"),
    "errors": ("error",),
    "double_plays": ("double_play", "double play"),
    "passed_balls": ("passed_ball", "passed ball"),
    "wild_pitches": ("wild_pitch", "wild pitch"),
    "stolen_bases": ("stolen_base", "stole "),
    "caught_stealing": ("caught_stealing", "caught stealing"),
    "pickoffs": ("pickoff", "picked off"),
    "runner_advancement": ("advance", "scored"),
}


def walk_json(value: Any, path: str = "$", array_sample: int = 25) -> Iterator[tuple[str, Any]]:
    yield path, value
    if isinstance(value, dict):
        for key, child in value.items():
            yield from walk_json(child, f"{path}.{key}", array_sample=array_sample)
    elif isinstance(value, list):
        for child in value[:array_sample]:
            yield from walk_json(child, f"{path}[]", array_sample=array_sample)


def schema_inventory(payloads: list[Any]) -> list[dict[str, Any]]:
    paths: dict[str, Counter[str]] = defaultdict(Counter)
    for payload in payloads:
        for path, value in walk_json(payload):
            paths[path][type(value).__name__] += 1
    return [
        {"path": path, "types": dict(sorted(types.items())), "observations": sum(types.values())}
        for path, types in sorted(paths.items())
    ]


def semantic_presence(payload: Any) -> dict[str, bool]:
    searchable: list[str] = []
    for path, value in walk_json(payload, array_sample=500):
        searchable.append(path.lower())
        if isinstance(value, str):
            searchable.append(value.lower())
    corpus = "\n".join(searchable)
    return {
        category: any(term in corpus for term in terms)
        for category, terms in SEMANTIC_TERMS.items()
    }


def count_plays(payload: Any) -> int:
    if isinstance(payload, dict) and isinstance(payload.get("plays"), list):
        return len(payload["plays"])
    if isinstance(payload, list):
        return len(payload)
    return 0


def count_boxscore_players(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    player_ids: set[str] = set()
    for _, value in walk_json(payload, array_sample=10_000):
        if isinstance(value, dict):
            player_id = value.get("player_id") or value.get("id")
            if player_id is not None and any(
                key in value for key in ("first_name", "last_name", "player_text", "stats")
            ):
                player_ids.add(str(player_id))
    return len(player_ids)


def payload_quality(boxscore: Any, plays: Any) -> tuple[int, int, int]:
    play_count = count_plays(plays)
    players = count_boxscore_players(boxscore)
    semantic = semantic_presence(plays)
    return play_count, players, sum(semantic.values())


def audit_authenticated_snapshot(project_root: Path, snapshot_id: str) -> dict[str, Any]:
    canonical_root = project_root / "data" / "snapshots" / snapshot_id / "public"
    raw_root = project_root / "data" / "raw" / "authenticated" / snapshot_id
    output = project_root / "data" / "snapshots" / snapshot_id / "audit"
    canonical_games = read_json(canonical_root / "canonical_games.json")
    crosswalk = read_json(canonical_root / "game_crosswalk.json")
    completed = {game["canonical_id"]: game for game in canonical_games if game["status"] == "completed"}
    by_contest: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in crosswalk:
        game = completed.get(row["canonical_id"])
        if game and row["source_game_id"] == game["preferred_source_game_id"]:
            by_contest[row["canonical_id"]].append(row)

    boxscores: list[Any] = []
    plays_payloads: list[Any] = []
    source_audit: list[dict[str, Any]] = []
    selected: list[dict[str, Any]] = []
    missing_files = 0
    for canonical_id, rows in sorted(by_contest.items()):
        candidates: list[dict[str, Any]] = []
        for row in rows:
            game_root = raw_root / "games" / row["source_game_id"]
            boxscore_path = game_root / "boxscore.json"
            plays_path = game_root / "plays.json"
            if not boxscore_path.exists() or not plays_path.exists():
                missing_files += int(not boxscore_path.exists()) + int(not plays_path.exists())
                source_audit.append(
                    {
                        **row,
                        "boxscore_present": boxscore_path.exists(),
                        "plays_present": plays_path.exists(),
                        "selected": False,
                    }
                )
                continue
            boxscore = read_json(boxscore_path)
            plays = read_json(plays_path)
            boxscores.append(boxscore)
            plays_payloads.append(plays)
            quality = payload_quality(boxscore, plays)
            semantics = semantic_presence(plays)
            candidate = {
                **row,
                "boxscore_present": True,
                "plays_present": True,
                "play_count": quality[0],
                "boxscore_player_count": quality[1],
                "semantic_categories_present": quality[2],
                "semantic_presence": semantics,
                "quality_tuple": quality,
            }
            candidates.append(candidate)
        if candidates:
            winner = max(candidates, key=lambda candidate: candidate["quality_tuple"])
            selected.append(
                {
                    "canonical_id": canonical_id,
                    "source_game_id": winner["source_game_id"],
                    "source_team_id": winner["source_team_id"],
                    "selection_quality": list(winner["quality_tuple"]),
                }
            )
            for candidate in candidates:
                candidate["selected"] = candidate is winner
                candidate["quality_tuple"] = list(candidate["quality_tuple"])
                source_audit.append(candidate)

    semantic_counts = Counter()
    for row in source_audit:
        if row.get("selected"):
            semantic_counts.update(
                key for key, present in row.get("semantic_presence", {}).items() if present
            )
    summary = {
        "snapshot_id": snapshot_id,
        "completed_canonical_contests": len(completed),
        "expected_selected_source_copies": sum(len(rows) for rows in by_contest.values()),
        "selected_analytical_copies": len(selected),
        "missing_endpoint_files": missing_files,
        "complete_contest_coverage": len(selected) / len(completed) if completed else 0.0,
        "semantic_selected_game_counts": dict(sorted(semantic_counts.items())),
    }
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "summary.json", summary)
    write_json(output / "source_copy_audit.json", source_audit)
    write_json(output / "analytical_copy_selection.json", selected)
    write_json(output / "boxscore_schema.json", schema_inventory(boxscores))
    write_json(output / "plays_schema.json", schema_inventory(plays_payloads))
    return summary
