from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import certifi

from .io import read_json, sha256_file, write_json


API_ROOT = "https://api.team-manager.gc.com"
# This browser API key is already embedded in the public GameChanger web client
# and in Scout Em Out's existing public-schedule client. It is not a user token.
PUBLIC_API_KEY = "AIzaSyAyHsuk1t0eBgrlufaCabpMrajaPgfZlNY"


class PublicFetchError(RuntimeError):
    pass


def fetch_json(path: str, retries: int = 3, delay_seconds: float = 1.5) -> Any:
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        headers={
            "Accept": "application/json",
            "User-Agent": "ScoutEmOut-AUSL-WAR-Research/0.1",
            "x-goog-api-key": PUBLIC_API_KEY,
        },
    )
    last_error: BaseException | None = None
    tls_context = ssl.create_default_context(cafile=certifi.where())
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=30, context=tls_context) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            last_error = error
            if attempt + 1 < retries:
                time.sleep(delay_seconds * (attempt + 1))
    raise PublicFetchError(f"Could not fetch {path}: {last_error}")


def _snapshot_id(now: datetime) -> str:
    return now.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def collect_public_snapshot(project_root: Path, now: datetime | None = None) -> Path:
    """Fetch public team lists and schedules into a new immutable snapshot."""
    now = now or datetime.now(timezone.utc)
    config = read_json(project_root / "config" / "sources.json")
    snapshot = project_root / "data" / "raw" / "public" / _snapshot_id(now)
    if snapshot.exists():
        raise FileExistsError(f"Snapshot already exists and will not be overwritten: {snapshot}")
    snapshot.mkdir(parents=True)

    organization_id = config["organization_2026"]["id"]
    organization_teams = fetch_json(f"/public/organizations/{organization_id}/teams")
    teams: list[dict[str, Any]] = []
    for team in organization_teams:
        teams.append(
            {
                "season": 2026,
                "id": team["id"],
                "name": team["name"],
                "source": "organization",
                "metadata": team,
            }
        )
    for team in config["historical_teams"]:
        teams.append({**team, "source": "configured_historical"})

    write_json(snapshot / "organization_2026.json", organization_teams)
    write_json(snapshot / "teams.json", teams)

    schedule_summary: list[dict[str, Any]] = []
    for index, team in enumerate(teams):
        games = fetch_json(f"/public/teams/{team['id']}/games")
        relative = Path("games") / str(team["season"]) / f"{team['id']}.json"
        write_json(snapshot / relative, games)
        schedule_summary.append(
            {
                "season": team["season"],
                "team_id": team["id"],
                "team_name": team["name"],
                "game_rows": len(games),
                "completed_rows": sum(g.get("game_status") == "completed" for g in games),
                "path": str(relative),
            }
        )
        if index + 1 < len(teams):
            time.sleep(1.5)

    write_json(snapshot / "schedule_summary.json", schedule_summary)
    files = sorted(path for path in snapshot.rglob("*.json") if path.name != "manifest.json")
    manifest = {
        "snapshot_id": snapshot.name,
        "fetched_at": now.astimezone(timezone.utc).isoformat(),
        "source": API_ROOT,
        "files": [
            {
                "path": str(path.relative_to(snapshot)),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ],
    }
    write_json(snapshot / "manifest.json", manifest)
    return snapshot
