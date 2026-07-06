#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import mimetypes
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import certifi

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ausl_war.io import write_json
from ausl_war.official import SEASON_IDS, canonical_person_key, official_stats


class HeadshotParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "img":
            return
        values = dict(attrs)
        alt = values.get("alt") or ""
        source = values.get("src") or values.get("data-src") or ""
        lower = alt.lower()
        if "headshot of " not in lower or not source or "default" in source.lower():
            return
        name = alt[lower.index("headshot of ") + len("headshot of ") :].strip()
        self.rows.append((name, source))


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AUSL-WAR-Research/1.0"})
    context = __import__("ssl").create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=45, context=context) as response:
        return response.read()


def main() -> None:
    destination = ROOT / "output" / "assets" / "headshots"
    audit = {"source": "official AUSL player directory", "seasons": {}}
    default_hashes = {
        hashlib.sha256(fetch("https://resource.auprosports.com/prod/players/default.png")).hexdigest(),
        hashlib.sha256(fetch("https://resource.auprosports.com/prod/players/999999/999999-ausl.png")).hexdigest(),
    }
    for season in (2025, 2026):
        url = f"https://theausl.com/players/?season={season}-ausl"
        html = fetch(url).decode("utf-8")
        parser = HeadshotParser()
        parser.feed(html)
        discovered: dict[str, list[tuple[str, str]]] = {}
        for name, source in parser.rows:
            discovered.setdefault(canonical_person_key(name), []).append((name, urljoin(url, source)))
        if not discovered:
            for source in official_stats(ROOT, "20260704T165430Z", season):
                if source.get("playerId") is None:
                    continue
                name = f"{source.get('firstName', '')} {source.get('lastName', '')}".strip()
                player_id = int(source["playerId"])
                for image_url in (
                    f"https://resource.auprosports.com/prod/players/{player_id}/{player_id}-ausl.png",
                    f"https://resource.auprosports.com/prod/players/{player_id}.png",
                ):
                    payload = fetch(image_url)
                    if hashlib.sha256(payload).hexdigest() not in default_hashes:
                        discovered.setdefault(canonical_person_key(name), []).append((name, image_url))
                        break
        players = json.loads((ROOT / "output" / f"combined_{season}.json").read_text())
        season_dir = destination / str(season)
        season_dir.mkdir(parents=True, exist_ok=True)
        mapping = {}
        ambiguous = {}
        for player in players:
            key = player["player_key"]
            choices = sorted(set(discovered.get(key, [])), key=lambda row: ("-ausl." not in row[1], row[1]))
            if not choices:
                continue
            if len({row[1] for row in choices}) > 1:
                ambiguous[key] = [row[1] for row in choices]
            name, image_url = choices[0]
            payload = fetch(image_url)
            suffix = Path(urlparse(image_url).path).suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
                suffix = mimetypes.guess_extension("image/png") or ".png"
            relative = Path("assets") / "headshots" / str(season) / f"{key}{suffix}"
            path = ROOT / "output" / relative
            path.write_bytes(payload)
            mapping[key] = {
                "player": player["player"],
                "official_name": name,
                "source_url": image_url,
                "local_path": relative.as_posix(),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        write_json(ROOT / "output" / f"headshots_{season}.json", mapping)
        audit["seasons"][str(season)] = {
            "leaderboard_players": len(players),
            "directory_headshots": len(discovered),
            "matched": len(mapping),
            "unmatched": [row["player"] for row in players if row["player_key"] not in mapping],
            "ambiguous": ambiguous,
            "source_url": url,
        }
    write_json(ROOT / "output" / "headshot_audit.json", audit)


if __name__ == "__main__":
    main()
