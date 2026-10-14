"""Host-neutral nightly entry point; running this command explicitly imports data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.db.session import SessionLocal
from app.services.pff_nightly_refresh import run_nightly_refresh
from app.services.pff_snapshot import load_identity_overrides


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Collect, archive, and automatically import a validated PFF board (writes database)"
    )
    parser.add_argument("--draft-year", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--min-prospects", type=int, default=150)
    browser = parser.add_mutually_exclusive_group()
    browser.add_argument("--storage-state", type=Path, help="Authorized secret session file outside git")
    browser.add_argument("--cdp-url", help="Local dedicated browser; matching season tab will be reloaded")
    parser.add_argument("--identity-map", type=Path, help="Reviewed source-key to existing-player overrides")
    args = parser.parse_args()
    overrides = None
    if args.identity_map is not None:
        try:
            overrides = load_identity_overrides(args.identity_map)
        except ValueError as exc:
            parser.error(str(exc))
    with SessionLocal() as session:
        report = run_nightly_refresh(
            session, draft_year=args.draft_year, output_dir=args.output_dir,
            min_prospects=args.min_prospects, storage_state=args.storage_state,
            cdp_url=args.cdp_url, overrides=overrides,
        )
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
