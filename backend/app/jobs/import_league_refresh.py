"""Preview or apply a complete, reviewed league-data manifest."""

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.league_data_refresh import LeagueRefreshManifest, import_league_refresh


def main() -> int:
    parser = argparse.ArgumentParser(description="Import reviewed projected order and team needs; dry-run by default")
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--manifest", type=Path)
    inputs.add_argument("--schema", action="store_true", help="Print the reviewed manifest JSON schema")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()
    if args.schema:
        if args.commit:
            parser.error("--commit requires --manifest")
        print(json.dumps(LeagueRefreshManifest.model_json_schema(), indent=2))
        return 0
    manifest = LeagueRefreshManifest.model_validate_json(args.manifest.read_text(encoding="utf-8-sig"))
    with SessionLocal() as session:
        report = import_league_refresh(session, manifest, commit=args.commit)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
