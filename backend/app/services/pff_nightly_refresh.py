"""One-shot, auditable PFF refresh for an external host scheduler."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from datetime import UTC, datetime
import json
import logging
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import ProspectBoardSnapshotRecord
from app.services.pff_browser_collector import collect_board
from app.services.pff_snapshot import SOURCE_NAME
from app.services.prospect_board_import import import_board_snapshot

logger = logging.getLogger(__name__)


@contextmanager
def refresh_lock(path: Path) -> Generator[None]:
    """Hold a process-lifetime host-local lock; crashes release the OS lock."""
    with path.open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_json(path: Path, payload: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(payload, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def run_nightly_refresh(
    session: Session,
    *,
    draft_year: int,
    output_dir: Path,
    min_prospects: int = 150,
    storage_state: Path | None = None,
    cdp_url: str | None = None,
    overrides: dict[str, str] | None = None,
) -> dict[str, object]:
    """Archive validated facts, then import atomically; every failure propagates."""
    if not 2020 <= draft_year <= 2100 or min_prospects < 1:
        raise ValueError("Invalid draft year or minimum prospect count")
    if cdp_url and storage_state is not None:
        raise ValueError("Choose a storage state or a local CDP connection, not both")
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid4().hex
    report_path = output_dir / f"pff-{draft_year}-{run_id}.run.json"
    snapshot_path = output_dir / f"pff-{draft_year}-{run_id}.snapshot.json"
    report: dict[str, object] = {
        "run_id": run_id, "draft_year": draft_year, "status": "running", "stage": "lock",
        "started_at": datetime.now(UTC).isoformat(), "report_path": str(report_path),
    }
    _write_json(report_path, report)
    try:
        # Every scheduled invocation for this database must share this directory.
        with refresh_lock(output_dir / ".pff-refresh.lock"):
            report["stage"] = "collect"
            snapshot = collect_board(
                draft_year, min_prospects, storage_state, cdp_url=cdp_url,
                refresh_existing=cdp_url is not None,
            )
            report["stage"] = "archive"
            _write_json(snapshot_path, snapshot.model_dump(mode="json"))
            report["snapshot_path"] = str(snapshot_path)
            report["prospect_count"] = len(snapshot.prospects)
            report["stage"] = "import"
            previous = session.scalar(
                select(ProspectBoardSnapshotRecord)
                .where(
                    ProspectBoardSnapshotRecord.source_name == SOURCE_NAME,
                    ProspectBoardSnapshotRecord.draft_year == draft_year,
                )
                .order_by(ProspectBoardSnapshotRecord.collected_at.desc())
                .limit(1)
            )
            if previous is not None and len(snapshot.prospects) < previous.prospect_count:
                raise ValueError(
                    f"PFF board shrank from {previous.prospect_count} to {len(snapshot.prospects)} rows; "
                    "review the archived snapshot before a manual import"
                )
            report["import"] = import_board_snapshot(session, snapshot, overrides, commit=True)
            report["status"] = "succeeded"
            report["stage"] = "complete"
            report["completed_at"] = datetime.now(UTC).isoformat()
            _write_json(report_path, report)
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        report["completed_at"] = datetime.now(UTC).isoformat()
        logger.exception("PFF refresh failed: run_id=%s stage=%s", run_id, report["stage"])
        _write_json(report_path, report)
        raise
    return report
