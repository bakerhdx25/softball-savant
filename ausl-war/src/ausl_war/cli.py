from __future__ import annotations

import argparse
import json
from pathlib import Path

from .audit import audit_authenticated_snapshot
from .canonical import canonicalize_snapshot
from .normalize import normalize_snapshot
from .official_pipeline import build_official_pipeline, build_official_tto_study
from .positional import build_positional_research
from .public import collect_public_snapshot
from .re24 import build_re24_snapshot
from .tto import build_tto_study
from .war import build_war_snapshot
from .validate import validate_snapshot


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def latest_public_snapshot(root: Path) -> Path:
    candidates = sorted((root / "data" / "raw" / "public").glob("*"))
    if not candidates:
        raise FileNotFoundError("No public snapshots found. Run fetch-public first.")
    return candidates[-1]


def main() -> None:
    parser = argparse.ArgumentParser(description="AUSL WAR research pipeline")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("fetch-public", help="capture a new immutable public schedule snapshot")
    canonical = subparsers.add_parser("canonicalize", help="deduplicate a public schedule snapshot")
    canonical.add_argument("--snapshot", type=Path, help="snapshot directory; defaults to latest")
    authenticated_audit = subparsers.add_parser(
        "audit-authenticated", help="audit raw boxscore/play coverage and schemas"
    )
    authenticated_audit.add_argument("--snapshot", required=True, help="public snapshot ID")
    normalize = subparsers.add_parser(
        "normalize-html", help="normalize newest-first HTML play text into base-out events"
    )
    normalize.add_argument("--snapshot", required=True, help="public snapshot ID")
    re24 = subparsers.add_parser("build-re24", help="estimate raw and smoothed AUSL RE24")
    re24.add_argument("--snapshot", required=True, help="public snapshot ID")
    re24.add_argument("--prior-pseudocount", type=float, default=20.0)
    war = subparsers.add_parser("build-war", help="calculate AUSL 2026 WAR components")
    war.add_argument("--snapshot", required=True, help="public snapshot ID")
    positions = subparsers.add_parser(
        "research-positions", help="audit and test AUSL positional-adjustment candidates"
    )
    positions.add_argument("--snapshot", required=True, help="public snapshot ID")
    validate = subparsers.add_parser("validate", help="run completion validation and reports")
    validate.add_argument("--snapshot", required=True, help="public snapshot ID")
    tto = subparsers.add_parser(
        "build-tto", help="build the isolated times-through-order research study"
    )
    tto.add_argument("--snapshot", required=True, help="normalized snapshot ID")
    official = subparsers.add_parser(
        "build-official-pipeline",
        help="fetch public AUSL data and build an official-only WAR/TTO snapshot",
    )
    official.add_argument("--snapshot", help="snapshot ID; defaults to current UTC timestamp")
    official_tto = subparsers.add_parser(
        "build-official-tto",
        help="build TTO outputs from an official-only normalized snapshot",
    )
    official_tto.add_argument("--snapshot", required=True, help="official-only snapshot ID")
    args = parser.parse_args()
    root = project_root()

    if args.command == "fetch-public":
        snapshot = collect_public_snapshot(root)
        print(snapshot)
    elif args.command == "canonicalize":
        snapshot = args.snapshot or latest_public_snapshot(root)
        output = root / "data" / "snapshots" / snapshot.name / "public"
        audit = canonicalize_snapshot(snapshot, output)
        print(json.dumps(audit, indent=2, sort_keys=True))
    elif args.command == "audit-authenticated":
        audit = audit_authenticated_snapshot(root, args.snapshot)
        print(json.dumps(audit, indent=2, sort_keys=True))
    elif args.command == "normalize-html":
        summary = normalize_snapshot(root, args.snapshot)
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "build-re24":
        summary = build_re24_snapshot(
            root,
            args.snapshot,
            prior_pseudocount=args.prior_pseudocount,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "build-war":
        summary = build_war_snapshot(
            root,
            args.snapshot,
        )
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "research-positions":
        result = build_positional_research(root, args.snapshot)
        print(json.dumps(result, indent=2, sort_keys=True))
    elif args.command == "validate":
        result = validate_snapshot(root, args.snapshot)
        print(json.dumps(result, indent=2, sort_keys=True))
        if not result["passed"]:
            raise SystemExit(1)
    elif args.command == "build-tto":
        summary = build_tto_study(root, args.snapshot)
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "build-official-pipeline":
        summary = build_official_pipeline(root, args.snapshot)
        print(json.dumps(summary, indent=2, sort_keys=True))
    elif args.command == "build-official-tto":
        summary = build_official_tto_study(root, args.snapshot)
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
