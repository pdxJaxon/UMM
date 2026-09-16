"""PostgreSQL-backed relational models for the draft domain."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    drafts = relationship("DraftRunRecord", back_populates="user")


class TeamRecord(Base):
    """Persisted NFL team record."""

    __tablename__ = "teams"

    id = Column(String(64), primary_key=True)
    name = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    abbreviation = Column(String(10), unique=True, nullable=False)
    draft_order = Column(Integer, nullable=False)


class PlayerRecord(Base):
    """Persisted draft prospect record."""

    __tablename__ = "players"

    id = Column(String(64), primary_key=True)
    first_name = Column(String(100), nullable=False)
    last_name = Column(String(100), nullable=False)
    position = Column(String(20), nullable=False)
    college_id = Column(String(64), nullable=False)
    draft_year = Column(Integer, nullable=False)
    eligibility_status = Column(String(30), default="eligible", nullable=False)


class DraftRunRecord(Base):
    """Persisted user-owned mock draft session."""

    __tablename__ = "draft_runs"

    id = Column(String(64), primary_key=True)
    user_id = Column(String(64), ForeignKey("users.id"), index=True, nullable=False)
    controlled_team_id = Column(String(64), ForeignKey("teams.id"), nullable=False)
    draft_year = Column(Integer, nullable=False)
    status = Column(String(20), default="drafting", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
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
    selected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    draft_run = relationship("DraftRunRecord", back_populates="picks")