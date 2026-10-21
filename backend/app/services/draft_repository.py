"""SQLAlchemy repository for persistent draft lifecycle operations."""

from __future__ import annotations

import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import CollegeRecord, DraftPickRecord, DraftRunRecord, DraftTradeRecord, PlayerRecord, TeamBoardEntryRecord, TeamBoardRecord, TeamRecord, TeamNeedRecord
from app.services.llm_prediction import OpenAICompatiblePredictionProvider, PredictionContext, PredictionProvider, predict_pick
from app.services.leadership_tendencies import get_effective_tendencies
from app.services.ranking_service import (
    candidates_within_team_need_reach,
    select_with_team_randomness,
)
from app.services.trade_engine import evaluate_trade
from app.services.prospect_pool import latest_projected_snapshot, pool_filter, snapshot_rankings
from app.db.college_seed import college_logo_url
from app.services.draft_order import draft_order_for_year, latest_league_refresh

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
        team_order = draft_order_for_year(self.session, draft_year)
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
            order_basis="projected-one-pick-per-team" if latest_league_refresh(self.session, draft_year) else "seeded-sample",
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

    def recommend(self, draft: DraftRunRecord) -> dict[str, object]:
        """Recommend, but never persist, a controlled-team pick from stored evidence."""
        picks = self._ordered_picks(draft.id)
        pick_number = len(picks) + 1
        if draft.status != "drafting" or self.current_team_id(len(picks), self._draft_order(draft)) != draft.controlled_team_id:
            raise ValueError("Recommendations are only available when your team is on the clock")
        selected = {pick.player_id for pick in picks}
        pool = {row["player_id"]: row for row in self.eligible_players(draft) if row["player_id"] not in selected}
        ordered_ids = self._available_board_candidates(draft, draft.controlled_team_id, selected)
        ordered_ids.extend(player_id for player_id in pool if player_id not in ordered_ids)
        if not ordered_ids:
            raise ValueError("No available prospects remain for a recommendation")
        available_ranks = {player_id: rank for rank, player_id in enumerate(ordered_ids, 1)}
        ordered_ids = self._apply_reach_limit(
            draft, draft.controlled_team_id, ordered_ids, pick_number,
        )
        pool = {player_id: pool[player_id] for player_id in ordered_ids}
        if self.prediction_provider is None:
            raise RuntimeError("AI recommendations are unavailable: LLM_API_KEY is not configured")
        candidates = self._candidate_context(ordered_ids, draft)
        for candidate in candidates:
            player = pool[str(candidate["player_id"])]
            candidate.update({
                "rank": available_ranks[str(candidate["player_id"])],
                "name": f"{player['first_name']} {player['last_name']}",
                "college_name": player["college_name"],
            })
        team = self.session.get(TeamRecord, draft.controlled_team_id)
        if team is None:
            raise ValueError("Controlled team does not exist")
        result = predict_pick(
            PredictionContext(
                team_id=team.id, team_name=team.name, draft_year=draft.draft_year,
                pick_number=pick_number, candidates=tuple(candidates),
                team_needs=tuple(self._team_needs(team.id, draft.draft_year)),
                team_tendencies=tuple(self._team_tendencies(team.id, draft.draft_year)),
                overall_randomness=float(draft.overall_randomness),
                team_randomness=float(draft.randomness_overrides.get(team.id, team.randomness_score or 0)),
            ),
            self.prediction_provider,
        )
        alternative_ids = []
        for alternative in result.alternatives:
            if (
                not isinstance(alternative, dict)
                or not isinstance(alternative.get("player_id"), str)
                or alternative["player_id"] not in pool
            ):
                raise ValueError("AI recommendation returned an unavailable alternative")
            player_id = alternative["player_id"]
            if player_id == result.selected_player_id or player_id in alternative_ids:
                raise ValueError("AI recommendation returned duplicate alternatives")
            alternative_ids.append(player_id)
        self.session.refresh(draft)
        current_picks = self._ordered_picks(draft.id)
        current_available = {
            row["player_id"] for row in self.eligible_players(draft)
        } - {pick.player_id for pick in current_picks}
        if (
            draft.status != "drafting" or len(current_picks) + 1 != pick_number
            or self.current_team_id(len(current_picks), self._draft_order(draft)) != team.id
            or not {result.selected_player_id, *alternative_ids} <= current_available
        ):
            raise ValueError("Draft availability changed while recommending; request a fresh recommendation")
        by_id = {str(candidate["player_id"]): candidate for candidate in candidates}
        return {
            "draft_run_id": draft.id, "team_id": team.id, "pick_number": pick_number,
            "recommended": by_id[result.selected_player_id],
            "alternatives": [by_id[player_id] for player_id in alternative_ids],
            "confidence": result.confidence, "reasoning_factors": result.reasoning_factors,
            "evidence": result.evidence, "provider": result.provider, "model": result.model,
            "rank_basis": "UMM default board, then pinned source order",
        }

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

    def auto_simulate(self, draft: DraftRunRecord, *, max_picks: int | None = None) -> None:
        """Select up to the requested count, stopping for the controlled team."""
        if max_picks is not None and max_picks < 1:
            raise ValueError("Maximum picks must be positive")
        picks = self._ordered_picks(draft.id)
        starting_count = len(picks)
        tendency_cache: dict[str, list[dict[str, object]]] = {}
        while draft.status != "completed" and self.current_team_id(len(picks), self._draft_order(draft)) != draft.controlled_team_id:
            if max_picks is not None and len(picks) - starting_count >= max_picks:
                break
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
            pick_number = len(picks) + 1
            remaining = self._apply_reach_limit(draft, team_id, remaining, pick_number)
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
                        pick_number=pick_number,
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
                "order_basis": draft.order_basis,
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
            select(PlayerRecord, CollegeRecord.name, CollegeRecord.abbreviation, CollegeRecord.logo_url)
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
                "college_logo_url": college_logo_url(player.college_id, logo_url) if logo_url is not None else None,
                "eligibility_status": player.eligibility_status,
                "is_projected": player.eligibility_status == "unconfirmed",
                "source_rank": rankings[player.id].overall_rank if player.id in rankings else None,
            }
            for player, college_name, college_abbreviation, logo_url in ordered_rows
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

    def _apply_reach_limit(
        self,
        draft: DraftRunRecord,
        team_id: str,
        candidates: list[str],
        pick_number: int,
    ) -> list[str]:
        """Restrict engine choices to a reachable need prospect and the BPA."""
        if not candidates:
            return []
        round_number = (pick_number - 1) // len(TEAM_ORDER) + 1
        positions = dict(
            self.session.execute(
                select(PlayerRecord.id, PlayerRecord.position)
                .where(PlayerRecord.id.in_(candidates))
            ).all()
        )
        board_ranks = self._candidate_board_ranks(draft, team_id)
        rankings = snapshot_rankings(self.session, draft.prospect_snapshot_id)
        fallback_rank = max(board_ranks.values(), default=0)
        missing_ids = [player_id for player_id in candidates if player_id not in board_ranks]
        for index, player_id in enumerate(missing_ids, 1):
            source_rank = rankings.get(player_id)
            board_ranks[player_id] = (
                source_rank.overall_rank
                if source_rank is not None and not fallback_rank
                else fallback_rank + index
            )
        return candidates_within_team_need_reach(
            candidates,
            positions,
            board_ranks,
            self._team_needs(team_id, draft.draft_year),
            round_number,
        )

    def _candidate_board_ranks(
        self,
        draft: DraftRunRecord,
        team_id: str,
    ) -> dict[str, int]:
        """Return active default-board ranks for this team's eligible players."""
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
            return {}
        entries = self.session.scalars(
            select(TeamBoardEntryRecord)
            .join(PlayerRecord, PlayerRecord.id == TeamBoardEntryRecord.player_id)
            .where(
                TeamBoardEntryRecord.board_id == board.id,
                TeamBoardEntryRecord.is_active.is_(True),
                pool_filter(draft.draft_year, draft.prospect_snapshot_id),
            )
        ).all()
        return {
            entry.player_id: entry.rank_position
            for entry in entries
            if (
                draft.prospect_snapshot_id is None
                or entry.score_breakdown.get("source_snapshot_id") == draft.prospect_snapshot_id
            )
        }

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
