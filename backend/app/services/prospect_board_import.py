"""Atomic, explicit import of validated external board snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    CollegeRecord, PlayerRecord, ProspectBoardRankingRecord, ProspectBoardSnapshotRecord,
    ProspectSourceIdentityRecord,
)
from app.services.pff_snapshot import (
    BoardSnapshot, ProspectRow, canonical_school, normalized_name,
)


@dataclass(frozen=True)
class ResolvedProspect:
    """An identity decision that can be reviewed before any writes."""

    row: ProspectRow
    player_id: str
    college_id: str
    canonical_position: str
    is_new_player: bool


def resolve_identities(
    session: Session, snapshot: BoardSnapshot, overrides: dict[str, str] | None = None,
) -> list[ResolvedProspect]:
    """Match persistent keys or unambiguous exact names/schools, never fuzzy names."""
    overrides = overrides or {}
    unknown_keys = set(overrides) - {row.key for row in snapshot.prospects}
    if unknown_keys:
        raise ValueError(f"Identity overrides contain keys not present in snapshot: {sorted(unknown_keys)}")
    players = list(session.scalars(select(PlayerRecord)))
    by_id = {player.id: player for player in players}
    by_name: dict[str, list[PlayerRecord]] = {}
    for player in players:
        by_name.setdefault(normalized_name(f"{player.first_name} {player.last_name}"), []).append(player)
    aliases = {
        identity.source_key: identity
        for identity in session.scalars(
            select(ProspectSourceIdentityRecord).where(
                ProspectSourceIdentityRecord.source_name == snapshot.source
            )
        )
    }
    snapshot_names: dict[str, int] = {}
    for row in snapshot.prospects:
        name = normalized_name(row.name)
        snapshot_names[name] = snapshot_names.get(name, 0) + 1
    colleges = set(session.scalars(select(CollegeRecord.id)))
    resolved = []
    for row in sorted(snapshot.prospects, key=lambda candidate: candidate.overall_rank):
        college_id = canonical_school(row.school)
        if college_id not in colleges:
            raise ValueError(f"College {college_id!r} is not seeded; initialize reference data before import")
        alias = aliases.get(row.key)
        override = overrides.get(row.key)
        if alias is not None and override is not None and alias.player_id != override:
            raise ValueError(f"Override conflicts with existing source mapping for {row.name}")
        if alias is not None and (
            alias.reviewed_name != normalized_name(row.name) or alias.reviewed_school != college_id
        ) and override is None:
            raise ValueError(f"Source identity changed for {row.name}; review the name/school and provide an override")
        player_id = override or (alias.player_id if alias is not None else None)
        if player_id is not None:
            player = by_id.get(player_id)
            if player is None:
                raise ValueError(f"Identity override or source mapping points to missing player {player_id}")
        else:
            candidates = by_name.get(normalized_name(row.name), [])
            if len(candidates) > 1 or snapshot_names[normalized_name(row.name)] > 1:
                raise ValueError(f"Ambiguous identity for {row.name}; provide a reviewed source-key override")
            player = candidates[0] if candidates else None
            if player is not None and player.college_id != college_id:
                raise ValueError(f"School changed for {row.name}; review transfer/identity and provide an override")
            player_id = player.id if player is not None else (
                "prospect-" + uuid5(NAMESPACE_URL, f"umm:{snapshot.source}:{row.key}").hex
            )
            if player is None and player_id in by_id:
                raise ValueError(f"Generated player ID already exists for {row.name}; review identity")
        if player is not None and player.draft_year != snapshot.draft_year:
            raise ValueError(f"Draft-year conflict for {row.name}; review eligibility before reusing this identity")
        resolved.append(ResolvedProspect(
            row, player_id, college_id, snapshot.position_map[row.position], player is None,
        ))
    if len({entry.player_id for entry in resolved}) != len(resolved):
        raise ValueError("Multiple source rows resolve to the same UMM player")
    return resolved


def import_board_snapshot(
    session: Session,
    snapshot: BoardSnapshot,
    overrides: dict[str, str] | None = None,
    commit: bool = False,
) -> dict[str, object]:
    """Dry-run by default; explicitly commit one validated snapshot when requested."""
    fingerprint = snapshot.content_hash()
    existing = session.scalar(
        select(ProspectBoardSnapshotRecord).where(ProspectBoardSnapshotRecord.content_hash == fingerprint)
    )
    if existing is not None:
        return {"status": "already_imported", "snapshot_id": existing.id, "prospect_count": existing.prospect_count}
    entries = resolve_identities(session, snapshot, overrides)
    snapshot_time = snapshot.collected_at.astimezone(UTC).replace(tzinfo=None)
    previous_snapshot = session.scalar(
        select(ProspectBoardSnapshotRecord)
        .where(
            ProspectBoardSnapshotRecord.source_name == snapshot.source,
            ProspectBoardSnapshotRecord.draft_year == snapshot.draft_year,
            ProspectBoardSnapshotRecord.collected_at < snapshot_time,
        )
        .order_by(ProspectBoardSnapshotRecord.collected_at.desc())
        .limit(1)
    )
    missing_from_previous_snapshot = []
    if previous_snapshot is not None:
        previous_rankings = session.execute(
            select(ProspectBoardRankingRecord, PlayerRecord)
            .join(PlayerRecord, PlayerRecord.id == ProspectBoardRankingRecord.player_id)
            .where(ProspectBoardRankingRecord.snapshot_id == previous_snapshot.id)
            .order_by(ProspectBoardRankingRecord.overall_rank)
        )
        current_player_ids = {entry.player_id for entry in entries}
        missing_from_previous_snapshot = [
            {
                "player_id": ranking.player_id,
                "name": f"{player.first_name} {player.last_name}",
                "previous_rank": ranking.overall_rank,
            }
            for ranking, player in previous_rankings
            if ranking.player_id not in current_player_ids
        ]
    report: dict[str, object] = {
        "status": "imported" if commit else "dry_run",
        "prospect_count": len(entries),
        "new_players": sum(entry.is_new_player for entry in entries),
        "existing_players": sum(not entry.is_new_player for entry in entries),
        "missing_grades": sum(getattr(entry.row, "pff_grade", None) is None for entry in entries),
        "missing_from_previous_snapshot": missing_from_previous_snapshot,
        "new_player_eligibility": "unconfirmed",
        "identities": [
            {"source_key": entry.row.key, "name": entry.row.name, "player_id": entry.player_id,
             "college_id": entry.college_id, "position": entry.canonical_position,
             "new_player": entry.is_new_player}
            for entry in entries
        ],
    }
    if not commit:
        return report
    snapshot_id = "board-snapshot-" + uuid4().hex
    with session.begin_nested():
        session.add(ProspectBoardSnapshotRecord(
            id=snapshot_id, content_hash=fingerprint, source_name=snapshot.source,
            source_url=snapshot.source_url, draft_year=snapshot.draft_year,
            collected_at=snapshot_time,
            source_updated_at_display=snapshot.source_updated_at_display,
            collection_method=snapshot.collection_method, scope=snapshot.scope,
            prospect_count=len(entries),
        ))
        for entry in entries:
            if entry.is_new_player:
                first_name, last_name = entry.row.name.split(maxsplit=1)
                session.add(PlayerRecord(
                    id=entry.player_id, first_name=first_name, last_name=last_name,
                    position=entry.canonical_position, college_id=entry.college_id,
                    draft_year=snapshot.draft_year, eligibility_status="unconfirmed",
                ))
        session.flush()
        for entry in entries:
            alias = session.scalar(select(ProspectSourceIdentityRecord).where(
                ProspectSourceIdentityRecord.source_name == snapshot.source,
                ProspectSourceIdentityRecord.source_key == entry.row.key,
            ))
            if alias is None:
                session.add(ProspectSourceIdentityRecord(
                    source_name=snapshot.source, source_key=entry.row.key,
                    player_id=entry.player_id, source_record_id=entry.row.source_record_id,
                    reviewed_name=normalized_name(entry.row.name), reviewed_school=entry.college_id,
                ))
            else:
                alias.reviewed_name = normalized_name(entry.row.name)
                alias.reviewed_school = entry.college_id
            session.add(ProspectBoardRankingRecord(
                snapshot_id=snapshot_id, player_id=entry.player_id,
                overall_rank=entry.row.overall_rank, pff_grade=getattr(entry.row, "pff_grade", None),
                source_name_display=entry.row.name, source_position=entry.row.position,
                source_school=entry.row.school, canonical_position=entry.canonical_position,
                college_id=entry.college_id,
            ))
        session.flush()
    session.commit()
    report["snapshot_id"] = snapshot_id
    return report
