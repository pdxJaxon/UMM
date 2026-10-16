"""SQLAlchemy repository for persistent draft lifecycle operations."""

from __future__ import annotations

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CollegeRecord, DraftPickRecord, DraftRunRecord, DraftTradeRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord, TeamRecord, TeamNeedRecord
from app.services.llm_prediction import OpenAICompatiblePredictionProvider, PredictionContext, PredictionProvider, predict_pick
from app.services.leadership_tendencies import get_effective_tendencies
from app.services.ranking_service import select_with_team_randomness
from app.services.trade_engine import evaluate_trade
from app.services.prospect_pool import latest_projected_snapshot, pool_filter, snapshot_rankings

TEAM_ORDER = tuple(f"team-{number}" for number in range(1, 33))


class DraftRepository:
    """Persist and retrieve draft state using a SQLAlchemy session."""

    def __init__(self, session: Session, prediction_provider: PredictionProvider | None = None) -> None:
        """Create a repository bound to one request-scoped database session."""
        self.session = session
        self.prediction_provider = prediction_provider
        if self.prediction_provider is None and settings.llm_api_key:
            self.prediction_provider = OpenAICompatiblePredictionProvider()

    def create(
        self,
        user_id: str,
        controlled_team_id: str,
        draft_year: int,
        randomness_overrides: dict[str, float] | None = None,
        overall_randomness: float = 50,
    ) -> DraftRunRecord:
        """Create a draft after validating its team and randomness overrides."""
        if self.session.get(TeamRecord, controlled_team_id) is None:
            raise ValueError("Controlled team does not exist")
        overrides = randomness_overrides or {}
        if not 0 <= float(overall_randomness) <= 100:
            raise ValueError("Overall randomness must be between 0 and 100")
        if any(not 0 <= float(value) <= 100 for value in overrides.values()):
            raise ValueError("Randomness overrides must be between 0 and 100")
        team_order = [team.id for team in self.session.scalars(select(TeamRecord).order_by(TeamRecord.draft_order))]
        if controlled_team_id not in team_order:
            raise ValueError("Controlled team does not have a draft position")
        snapshot = latest_projected_snapshot(self.session, draft_year)
        snapshot_id = snapshot.id if snapshot is not None else None
        eligible_prospects = self.session.scalar(
            select(func.count()).select_from(PlayerRecord).where(
                pool_filter(draft_year, snapshot_id),
            )
        ) or 0
        if eligible_prospects < len(team_order):
            raise ValueError(f"At least {len(team_order)} eligible prospects are required for a first-round draft (confirmed or approved projected)")
        draft = DraftRunRecord(
            id=self._next_id("draft"), user_id=user_id, controlled_team_id=controlled_team_id,
            draft_year=draft_year, status="drafting", overall_randomness=overall_randomness,
            randomness_overrides=overrides, draft_order=team_order,
            prospect_snapshot_id=snapshot_id,
        )
        self.session.add(draft)
        self.session.flush()
        return draft

    def get_owned(self, draft_id: str, user_id: str) -> DraftRunRecord:
        """Return a draft only when it exists and belongs to the requesting user."""
        draft = self.session.get(DraftRunRecord, draft_id)
        if draft is None:
            raise LookupError("Draft not found")
        if draft.user_id != user_id:
            raise PermissionError("Draft access denied")
        return draft

    def add_pick(
        self,
        draft: DraftRunRecord,
        team_id: str,
        player_id: str,
        source: str,
        randomness_factor: float = 0,
        prediction_metadata: dict[str, object] | None = None,
    ) -> DraftPickRecord:
        """Persist a unique pick and enforce the current draft order."""
        picks = self._ordered_picks(draft.id)
        player = self.session.get(PlayerRecord, player_id)
        if player is None:
            raise ValueError("Player does not exist")
        if player.draft_year != draft.draft_year:
            raise ValueError("Player is not part of this draft year")
        if self.session.scalar(select(PlayerRecord.id).where(
            PlayerRecord.id == player_id, pool_filter(draft.draft_year, draft.prospect_snapshot_id),
        )) is None:
            raise ValueError("Player is not eligible for this draft")
        if any(pick.player_id == player_id for pick in picks):
            raise ValueError("Player has already been selected")
        if team_id != self.current_team_id(len(picks), self._draft_order(draft)):
            raise ValueError("That team is not currently on the clock")
        pick_number = len(picks) + 1
        pick = DraftPickRecord(
            id=f"{draft.id}-pick-{pick_number}", draft_run_id=draft.id, pick_number=pick_number,
            round_number=((pick_number - 1) // len(TEAM_ORDER)) + 1, team_id=team_id,
            player_id=player_id, selection_source=source, randomness_factor=randomness_factor,
            prediction_metadata=prediction_metadata or {},
        )
        self.session.add(pick)
        if pick_number >= len(self._draft_order(draft)):
            draft.status = "completed"
        self.session.flush()
        return pick

    def auto_simulate(self, draft: DraftRunRecord) -> None:
        """Select available players until the controlled team is on the clock."""
        picks = self._ordered_picks(draft.id)
        tendency_cache: dict[str, list[dict[str, object]]] = {}
        while draft.status != "completed" and self.current_team_id(len(picks), self._draft_order(draft)) != draft.controlled_team_id:
            selected = {pick.player_id for pick in picks}
            pick_index = len(picks)
            self._maybe_execute_trade(draft, pick_index, tendency_cache)
            team_id = self.current_team_id(pick_index, self._draft_order(draft))
            if team_id == draft.controlled_team_id:
                break
            remaining = self._available_board_candidates(draft, team_id, selected)
            if not remaining:
                remaining = [
                    player["player_id"] for player in self.eligible_players(draft)
                    if player["player_id"] not in selected
                ]
            if not remaining:
                raise ValueError("No available prospects remain before the first round is complete")
            team = self.session.get(TeamRecord, team_id)
            baseline = float(team.randomness_score or 0) if team else 50.0
            randomness = self._effective_randomness(
                draft.overall_randomness,
                draft.randomness_overrides.get(team_id, baseline),
            )
            source = "FALLBACK"
            metadata: dict[str, object] = {"mode": "deterministic-fallback"}
            if self.prediction_provider is not None:
                prediction = predict_pick(
                    PredictionContext(
                        team_id=team_id,
                        team_name=team.name if team else team_id,
                        draft_year=draft.draft_year,
                        pick_number=len(picks) + 1,
                        candidates=tuple(self._candidate_context(remaining, draft)),
                        team_needs=tuple(self._team_needs(team_id, draft.draft_year)),
                        team_tendencies=tuple(self._cached_team_tendencies(team_id, draft.draft_year, tendency_cache)),
                        overall_randomness=float(draft.overall_randomness),
                        team_randomness=float(draft.randomness_overrides.get(team_id, team.randomness_score or 50)) if team else 50,
                    ),
                    self.prediction_provider,
                )
                player_id = prediction.selected_player_id
                applied_randomness = prediction.randomness
                source = "LLM"
                metadata = {
                    "provider": prediction.provider,
                    "model": prediction.model,
                    "prompt_version": prediction.prompt_version,
                    "confidence": prediction.confidence,
                    "alternatives": prediction.alternatives,
                    "reasoning_factors": prediction.reasoning_factors,
                    "evidence": prediction.evidence,
                }
            else:
                player_id, applied_randomness = select_with_team_randomness(remaining, randomness, random.Random())
            self.add_pick(draft, team_id, player_id, source, applied_randomness, metadata)
            picks = self._ordered_picks(draft.id)

    def state(self, draft: DraftRunRecord) -> dict[str, object]:
        """Return API-ready state for a persisted draft."""
        picks = self._ordered_picks(draft.id)
        return {
            "draft_run": {
                "id": draft.id,
                "user_id": draft.user_id,
                "controlled_team_id": draft.controlled_team_id,
                "season_year": draft.draft_year,
                "status": draft.status,
                "overall_randomness": float(draft.overall_randomness),
                "randomness_overrides": draft.randomness_overrides,
                "draft_order": self._draft_order(draft),
                "prospect_snapshot_id": draft.prospect_snapshot_id,
            },
            "current_pick_number": len(picks) + 1,
            "current_team_id": self.current_team_id(len(picks), self._draft_order(draft)),
            "picks": [{"id": p.id, "draft_run_id": p.draft_run_id, "pick_number": p.pick_number, "round_number": p.round_number, "team_id": p.team_id, "player_id": p.player_id, "selection_source": p.selection_source, "randomness_factor": float(p.randomness_factor), "prediction_metadata": p.prediction_metadata} for p in picks],
            "trades": [
                {
                    "id": trade.id,
                    "trade_number": trade.trade_number,
                    "pick_number": trade.pick_number,
                    "acquired_pick_number": trade.acquired_pick_number,
                    "moving_up_team_id": trade.moving_up_team_id,
                    "moving_down_team_id": trade.moving_down_team_id,
                    "direction": trade.direction,
                    "current_pick_value": float(trade.current_pick_value),
                    "acquired_pick_value": float(trade.acquired_pick_value),
                    "value_delta": float(trade.value_delta),
                    "tendency_evidence": trade.tendency_evidence,
                }
                for trade in self._ordered_trades(draft.id)
            ],
        }

    def eligible_players(self, draft: DraftRunRecord) -> list[dict[str, object]]:
        """Return all eligible players for a draft year, independent of team boards."""
        rows = self.session.execute(
            select(PlayerRecord, CollegeRecord.name, CollegeRecord.abbreviation)
            .outerjoin(CollegeRecord, CollegeRecord.id == PlayerRecord.college_id)
            .where(
                pool_filter(draft.draft_year, draft.prospect_snapshot_id),
            )
            .order_by(PlayerRecord.id)
        ).all()
        rankings = snapshot_rankings(self.session, draft.prospect_snapshot_id)
        ordered_rows = sorted(rows, key=lambda row: (
            rankings[row[0].id].overall_rank if row[0].id in rankings else float("inf"), row[0].id,
        ))
        return [
            {
                "player_id": player.id,
                "first_name": player.first_name,
                "last_name": player.last_name,
                "position": player.position,
                "college_name": college_name,
                "college_abbreviation": college_abbreviation,
                "eligibility_status": player.eligibility_status,
                "is_projected": player.eligibility_status == "unconfirmed",
                "source_rank": rankings[player.id].overall_rank if player.id in rankings else None,
            }
            for player, college_name, college_abbreviation in ordered_rows
        ]

    @staticmethod
    def current_team_id(pick_count: int, draft_order: list[str] | None = None) -> str:
        """Return the team assigned to the next pick."""
        order = draft_order or list(TEAM_ORDER)
        return "" if pick_count >= len(order) else order[pick_count % len(order)]

    def _draft_order(self, draft: DraftRunRecord) -> list[str]:
        """Return the persisted order, with compatibility for pre-trade runs."""
        return list(draft.draft_order or TEAM_ORDER)

    def _maybe_execute_trade(
        self,
        draft: DraftRunRecord,
        pick_index: int,
        tendency_cache: dict[str, list[dict[str, object]]],
    ) -> DraftTradeRecord | None:
        """Apply the strongest qualifying trade before the current pick."""
        order = self._draft_order(draft)
        tendencies = {
            team_id: self._cached_team_tendencies(team_id, draft.draft_year, tendency_cache)
            for team_id in set(order)
        }
        proposal = evaluate_trade(order, pick_index, tendencies)
        if proposal is None:
            return None
        later_index = next(
            index for index in range(pick_index + 1, len(order))
            if order[index] == proposal.moving_up_team_id
        )
        order[pick_index], order[later_index] = order[later_index], order[pick_index]
        draft.draft_order = order
        trade_number = len(self._ordered_trades(draft.id)) + 1
        trade = DraftTradeRecord(
            id=f"{draft.id}-trade-{trade_number}",
            draft_run_id=draft.id,
            trade_number=trade_number,
            pick_number=proposal.current_pick_number,
            acquired_pick_number=proposal.acquired_pick_number,
            moving_up_team_id=proposal.moving_up_team_id,
            moving_down_team_id=proposal.moving_down_team_id,
            direction="UP_DOWN",
            current_pick_value=proposal.current_pick_value,
            acquired_pick_value=proposal.acquired_pick_value,
            value_delta=proposal.value_delta,
            tendency_evidence=proposal.evidence,
        )
        self.session.add(trade)
        self.session.flush()
        return trade

    def _ordered_trades(self, draft_id: str) -> list[DraftTradeRecord]:
        """Load executed trades in their immutable event order."""
        statement = select(DraftTradeRecord).where(DraftTradeRecord.draft_run_id == draft_id).order_by(DraftTradeRecord.trade_number)
        return list(self.session.scalars(statement))

    def _ordered_picks(self, draft_id: str) -> list[DraftPickRecord]:
        """Load a draft's picks in immutable pick order."""
        statement = select(DraftPickRecord).where(DraftPickRecord.draft_run_id == draft_id).order_by(DraftPickRecord.pick_number)
        return list(self.session.scalars(statement))

    def _available_board_candidates(
        self,
        draft: DraftRunRecord,
        team_id: str,
        selected: set[str],
    ) -> list[str]:
        """Return available players from the latest generated team board."""
        board = self.session.scalar(
            select(TeamBoardRecord)
            .where(
                TeamBoardRecord.team_id == team_id,
                TeamBoardRecord.draft_year == draft.draft_year,
                TeamBoardRecord.board_type == "default",
            )
            .order_by(TeamBoardRecord.version.desc())
            .limit(1)
        )
        if board is None:
            return []
        entries = self.session.scalars(
            select(TeamBoardEntryRecord)
            .join(PlayerRecord, PlayerRecord.id == TeamBoardEntryRecord.player_id)
            .where(
                TeamBoardEntryRecord.board_id == board.id,
                TeamBoardEntryRecord.is_active.is_(True),
                pool_filter(draft.draft_year, draft.prospect_snapshot_id),
            )
            .order_by(TeamBoardEntryRecord.rank_position)
        ).all()
        return [
            entry.player_id for entry in entries
            if entry.player_id not in selected and (
                draft.prospect_snapshot_id is None
                or entry.score_breakdown.get("source_snapshot_id") == draft.prospect_snapshot_id
            )
        ]

    def _next_id(self, prefix: str) -> str:
        """Generate a collision-resistant identifier within the current database."""
        return f"{prefix}-{self.session.query(DraftRunRecord).count() + 1}"

    def _candidate_context(self, player_ids: list[str], draft: DraftRunRecord) -> list[dict[str, object]]:
        """Build compact, source-backed candidate context for the model."""
        rankings = snapshot_rankings(self.session, draft.prospect_snapshot_id)
        return [
            {
                "player_id": player_id,
                "position": player.position,
                "college_id": player.college_id,
                "source_rank": rankings[player_id].overall_rank if player_id in rankings else None,
                "is_projected": player.eligibility_status == "unconfirmed",
            }
            for player_id in player_ids
            if (player := self.session.get(PlayerRecord, player_id)) is not None
        ]

    def _team_needs(self, team_id: str, draft_year: int) -> list[dict[str, object]]:
        """Load active needs into model-safe dictionaries."""
        needs = self.session.scalars(
            select(TeamNeedRecord).where(
                TeamNeedRecord.team_id == team_id,
                TeamNeedRecord.draft_year == draft_year,
                TeamNeedRecord.is_active.is_(True),
            )
        ).all()
        return [{"position_code": need.position_code, "need_score": float(need.need_score), "source_name": need.source_name} for need in needs]

    def _team_tendencies(self, team_id: str, draft_year: int) -> list[dict[str, object]]:
        """Load active historical tendencies into model-safe dictionaries."""
        return get_effective_tendencies(self.session, team_id, draft_year)

    def _cached_team_tendencies(
        self,
        team_id: str,
        draft_year: int,
        cache: dict[str, list[dict[str, object]]],
    ) -> list[dict[str, object]]:
        """Reuse a team's effective tendencies throughout one simulation request."""
        if team_id not in cache:
            cache[team_id] = self._team_tendencies(team_id, draft_year)
        return cache[team_id]

    @staticmethod
    def _effective_randomness(overall_randomness: float, team_randomness: float) -> float:
        """Shift the team profile around the user's overall randomness baseline."""
        return min(max(float(overall_randomness) + float(team_randomness) - 50.0, 0.0), 100.0)
