"""PostgreSQL-backed relational models for the draft domain."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from app.db.session import Base


class UserRecord(Base):
    """Persisted user account record."""

    __tablename__ = "users"

    id = Column(String(64), primary_key=True)
    email = Column(String(320), unique=True, index=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    drafts = relationship("DraftRunRecord", back_populates="user")


class TeamRecord(Base):
    """Persisted NFL team record."""

    __tablename__ = "teams"

    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    abbreviation = Column(String(10), unique=True, nullable=False)
    draft_order = Column(Integer, nullable=False)
    logo_url = Column(String(500), nullable=False)
    helmet_url = Column(String(500), nullable=True)
    official_url = Column(String(500), nullable=False)
    randomness_score = Column(Numeric(5, 2), nullable=False, default=50)
    draft_needs = relationship("TeamNeedRecord", back_populates="team", cascade="all, delete-orphan")
    drafting_tendencies = relationship("TeamDraftingTendencyRecord", back_populates="team", cascade="all, delete-orphan")
    boards = relationship("TeamBoardRecord", back_populates="team", cascade="all, delete-orphan")


class TeamNeedRecord(Base):
    """Season-scoped team need with role-specific criticality."""

    __tablename__ = "team_needs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True)
    draft_year = Column(Integer, nullable=False, index=True)
    position_code = Column(String(20), nullable=False)
    role_level = Column(String(30), nullable=False)
    need_score = Column(Numeric(5, 2), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    rationale = Column(String(500), nullable=True)
    observed_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    team = relationship("TeamRecord", back_populates="draft_needs")


class TeamBoardRecord(Base):
    """Versioned default or user-customized board for one team and season."""

    __tablename__ = "team_boards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.id"), nullable=True, index=True)
    draft_year = Column(Integer, nullable=False, index=True)
    board_type = Column(String(20), nullable=False, default="default")
    version = Column(Integer, nullable=False, default=1)
    generated_at = Column(DateTime, nullable=False)
    scoring_version = Column(String(50), nullable=False)
    scoring_weights = Column(JSON, nullable=False, default=dict)
    team = relationship("TeamRecord", back_populates="boards")
    entries = relationship("TeamBoardEntryRecord", back_populates="board", cascade="all, delete-orphan")


class TeamBoardEntryRecord(Base):
    """Ranked player entry with an explainable score breakdown."""

    __tablename__ = "team_board_entries"
    __table_args__ = (UniqueConstraint("board_id", "player_id", name="uq_team_board_player"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    board_id = Column(Integer, ForeignKey("team_boards.id"), nullable=False, index=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    rank_position = Column(Integer, nullable=False)
    score = Column(Numeric(8, 3), nullable=False)
    score_breakdown = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)
    board = relationship("TeamBoardRecord", back_populates="entries")


class TeamDraftingTendencyRecord(Base):
    """Auditable team preference rule derived from historical draft behavior."""

    __tablename__ = "team_drafting_tendencies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True)
    draft_year = Column(Integer, nullable=True, index=True)
    tendency_type = Column(String(40), nullable=False)
    position_code = Column(String(20), nullable=True)
    metric_name = Column(String(60), nullable=True)
    target_value = Column(String(150), nullable=True)
    minimum_value = Column(Numeric(8, 2), nullable=True)
    maximum_value = Column(Numeric(8, 2), nullable=True)
    preference_score = Column(Numeric(5, 2), nullable=False)
    confidence_score = Column(Numeric(5, 2), nullable=False, default=0)
    sample_size = Column(Integer, nullable=False, default=0)
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    rationale = Column(String(500), nullable=True)
    observed_at = Column(DateTime, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    team = relationship("TeamRecord", back_populates="drafting_tendencies")


class TeamProspectMeetingRecord(Base):
    """Auditable meeting event between an NFL team and draft prospect."""

    __tablename__ = "team_prospect_meetings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    draft_year = Column(Integer, nullable=False, index=True)
    meeting_type = Column(String(60), nullable=False)
    importance_score = Column(Numeric(5, 2), nullable=False)
    occurred_at = Column(DateTime, nullable=True)
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    notes = Column(String(500), nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    is_active = Column(Boolean, nullable=False, default=True)


class ExternalMockPickRecord(Base):
    """Historical external mock selection used for consensus analysis."""

    __tablename__ = "external_mock_picks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    mock_id = Column(String(150), nullable=False)
    draft_year = Column(Integer, nullable=False, index=True)
    pick_number = Column(Integer, nullable=False, index=True)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False, index=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False)
    raw_payload = Column(JSON, nullable=False, default=dict)


class ProspectRefreshRunRecord(Base):
    """Audit record for one scheduled or manually triggered prospect refresh."""

    __tablename__ = "prospect_refresh_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    draft_year = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    processed_count = Column(Integer, nullable=False, default=0)
    source_names = Column(JSON, nullable=False, default=list)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)


class CollegeRecord(Base):
    """Persisted FBS college football program record."""

    __tablename__ = "colleges"

    id = Column(String(100), primary_key=True)
    name = Column(String(150), nullable=False)
    abbreviation = Column(String(20), unique=True, nullable=False)
    conference = Column(String(80), nullable=False)
    division = Column(String(20), nullable=False, default="FBS")
    logo_url = Column(String(500), nullable=False)
    official_url = Column(String(500), nullable=False)


class PositionImportanceRecord(Base):
    """Versioned baseline importance score for an NFL position group."""

    __tablename__ = "position_importance"

    position_code = Column(String(20), primary_key=True)
    display_name = Column(String(80), nullable=False)
    importance_score = Column(Numeric(5, 2), nullable=False)
    weighting_version = Column(String(40), nullable=False)
    rationale = Column(String(500), nullable=False)


class PlayerRecord(Base):
    """Persisted draft prospect record."""

    __tablename__ = "players"

    id = Column(String(64), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    position = Column(String(20), nullable=False)
    college_id = Column(String(100), ForeignKey("colleges.id"), nullable=False)
    draft_year = Column(Integer, nullable=False)
    eligibility_status = Column(String(30), default="eligible", nullable=False)
    birth_date = Column(DateTime, nullable=True)
    measurements = relationship("PlayerMeasurementRecord", back_populates="player", cascade="all, delete-orphan")
    athletic_scores = relationship("PlayerAthleticScoreRecord", back_populates="player", cascade="all, delete-orphan")
    derogatory_concerns = relationship("PlayerDerogatoryConcernRecord", back_populates="player", cascade="all, delete-orphan")


class PlayerDerogatoryConcernRecord(Base):
    """Auditable negative-issue record with explicit severity and confidence."""

    __tablename__ = "player_derogatory_concerns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    category = Column(String(60), nullable=False)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    severity = Column(String(20), nullable=False)
    confidence = Column(String(20), nullable=False, default="reported")
    status = Column(String(20), nullable=False, default="open")
    source_name = Column(String(100), nullable=False)
    source_url = Column(String(500), nullable=True)
    occurred_at = Column(DateTime, nullable=True)
    reported_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    player = relationship("PlayerRecord", back_populates="derogatory_concerns")


class PlayerMeasurementRecord(Base):
    """Append-only physical measurement snapshot from a named source."""

    __tablename__ = "player_measurements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False)
    source_name = Column(String(100), nullable=False)
    source_record_id = Column(String(150), nullable=True)
    age_years = Column(Numeric(5, 2), nullable=True)
    height_inches = Column(Numeric(5, 2), nullable=True)
    weight_lbs = Column(Numeric(6, 2), nullable=True)
    hand_inches = Column(Numeric(5, 2), nullable=True)
    arm_inches = Column(Numeric(5, 2), nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    player = relationship("PlayerRecord", back_populates="measurements")


class PlayerAthleticScoreRecord(Base):
    """Append-only athletic score snapshot such as RAS or SPARQ."""

    __tablename__ = "player_athletic_scores"

    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False)
    source_name = Column(String(100), nullable=False)
    metric_name = Column(String(80), nullable=False)
    score = Column(Numeric(8, 3), nullable=True)
    score_scale = Column(String(40), nullable=True)
    raw_payload = Column(JSON, nullable=False, default=dict)
    player = relationship("PlayerRecord", back_populates="athletic_scores")


class DraftRunRecord(Base):
    """Persisted user-owned mock draft session."""

    __tablename__ = "draft_runs"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), index=True, nullable=False)
    controlled_team_id = Column(String(64), ForeignKey("teams.id"), nullable=False)
    draft_year = Column(Integer, nullable=False)
    status = Column(String(20), default="drafting", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    randomness_overrides = Column(JSON, nullable=False, default=dict)
    user = relationship("UserRecord", back_populates="drafts")
    picks = relationship("DraftPickRecord", back_populates="draft_run", cascade="all, delete-orphan")


class DraftPickRecord(Base):
    """Persisted player selection within a draft run."""

    __tablename__ = "draft_picks"
    __table_args__ = (UniqueConstraint("draft_run_id", "player_id", name="uq_draft_player"),)

    id = Column(String(64), primary_key=True)
    draft_run_id = Column(String(64), ForeignKey("draft_runs.id"), index=True, nullable=False)
    pick_number = Column(Integer, nullable=False)
    round_number = Column(Integer, nullable=False)
    team_id = Column(String(64), ForeignKey("teams.id"), nullable=False)
    player_id = Column(String(64), ForeignKey("players.id"), nullable=False)
    selection_source = Column(String(30), nullable=False)
    randomness_factor = Column(Numeric(5, 2), nullable=False, default=0)
    selected_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    draft_run = relationship("DraftRunRecord", back_populates="picks")