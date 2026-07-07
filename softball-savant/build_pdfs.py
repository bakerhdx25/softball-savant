#!/usr/bin/env python3
"""Generate Softball Savant scouting PDFs from the current site payload.

The browser pages and PDFs must use the same source of truth.  This script
loads ``data/site-data.json`` and reuses the existing scouting-report PDF
renderer, with its paths redirected into ``softball-savant``.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parent
REPO_ROOT = ROOT.parent
SITE_DATA_PATH = ROOT / "data" / "site-data.json"
OUTPUT_DIR = ROOT / "output" / "pdf"
FIELD_IMAGE = ROOT / "assets" / "field-clean-v2.svg"
LEGACY_RENDERER_PATH = REPO_ROOT / "ausl-scouting-web" / "build_pdfs.py"
LEGACY_LOGO_DIR = REPO_ROOT / "ausl-scouting-web" / "assets" / "logos"
PDF_PERIODS = ("2026", "combined")


def load_site_data() -> dict[str, Any]:
    if not SITE_DATA_PATH.is_file():
        raise FileNotFoundError(f"Missing site payload: {SITE_DATA_PATH}")
    return json.loads(SITE_DATA_PATH.read_text(encoding="utf-8"))


def load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ausl_scouting_pdf_renderer", LEGACY_RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load PDF renderer from {LEGACY_RENDERER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # The renderer's drawing code is still valid, but its default paths point
    # at the old standalone scouting site. Redirect every path that affects
    # generated output or assets so the PDFs match Softball Savant data.
    module.ROOT = ROOT
    module.OUTPUT_DIR = OUTPUT_DIR
    module.FIELD_IMAGE = FIELD_IMAGE
    module.LOGO_DIR = LEGACY_LOGO_DIR
    return module


def generate_pdfs(site: dict[str, Any]) -> list[Path]:
    renderer = load_renderer()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    for period_key in PDF_PERIODS:
        data = site["periods"][period_key]
        for team in data["teams"]:
            if not team.get("pdf"):
                continue
            outputs.append(renderer.generate_team(team, data))

    return outputs


def main() -> None:
    outputs = generate_pdfs(load_site_data())
    print(f"Generated {len(outputs)} Softball Savant PDFs in {OUTPUT_DIR.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
