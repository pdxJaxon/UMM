"""Validated PFF board snapshots and conservative source-to-domain mappings."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from datetime import UTC, datetime
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.college_seed import COLLEGES

SOURCE_NAME = "pff-big-board"
POSITION_MAP = {
    "QB": "QB", "HB": "RB", "RB": "RB", "FB": "FB", "WR": "WR", "TE": "TE",
    "T": "OT", "OT": "OT", "G": "IOL", "C": "IOL", "IOL": "IOL",
    "ED": "EDGE", "EDGE": "EDGE", "DI": "DT", "DT": "DT",
    "LB": "LB", "CB": "CB", "S": "S", "K": "K", "P": "P", "LS": "LS",
}
SCHOOL_ALIASES = {
    "miami (fl)": "miami", "miami (fl.)": "miami", "miami (oh)": "miami-ohio",
    "mississippi": "ole-miss", "southern california": "usc",
    "central florida": "ucf", "brigham young": "byu", "texas christian": "tcu",
    "southern methodist": "smu", "pitt": "pittsburgh",
    "uconn": "connecticut", "massachusetts": "umass",
}


def normalized_name(value: str) -> str:
    """Normalize case and whitespace without discarding meaningful name suffixes."""
    return " ".join(unicodedata.normalize("NFC", value).casefold().split())


def source_key(name: str, school: str, source_record_id: str | None = None) -> str:
    """Build a source key that never depends on a player's changing rank."""
    if source_record_id:
        return f"id:{source_record_id}"
    identity = json.dumps([normalized_name(name), normalized_name(school)], ensure_ascii=True)
    return "name-school:" + hashlib.sha256(identity.encode()).hexdigest()


def canonical_school(value: str) -> str:
    """Resolve only known college names and explicit aliases; never guess a school."""
    key = normalized_name(value)
    schools = {normalized_name(row["name"]): row["id"] for row in COLLEGES}
    schools.update({row["id"]: row["id"] for row in COLLEGES})
    school_id = SCHOOL_ALIASES.get(key) or schools.get(key)
    if school_id is None:
        raise ValueError(f"Unknown prospect school {value!r}; add a reviewed school mapping")
    return school_id


class ProspectRow(BaseModel):
    """Factual identity and ranking fields from an external prospect board."""
        raise ValueError(f"Unknown PFF school {value!r}; add a reviewed school mapping")
    return school_id


class PFFProspectRow(BaseModel):
    """Factual row fields exposed by the rendered PFF board."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False, frozen=True)

    source_record_id: str | None = Field(default=None, min_length=1, max_length=150)
    overall_rank: int = Field(strict=True, ge=1)
    name: str = Field(min_length=1, max_length=200)
    position: str = Field(min_length=1, max_length=20)
    school: str = Field(min_length=1, max_length=150)
    pff_grade: float | None = Field(default=None, strict=True, ge=0, le=100)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        """Require enough identity information for the existing player schema."""
        if len(value.split()) < 2:
            raise ValueError("Prospect requires a full name")
        return value

    @property
    def key(self) -> str:
        return source_key(self.name, self.school, self.source_record_id)


PFFProspectRow = ProspectRow


class BoardSnapshot(BaseModel):
    """Source-neutral dated board; inclusion does not imply draft eligibility."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)
    position_map: ClassVar[dict[str, str]] = POSITION_MAP

    source: str = Field(min_length=1, max_length=100)
class PFFBoardSnapshot(BaseModel):
    """Dated source data; validation does not imply declared draft eligibility."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, frozen=True)

    source: str = SOURCE_NAME
    source_url: str = Field(max_length=500)
    draft_year: int = Field(strict=True, ge=2020, le=2100)
    collected_at: datetime
    source_updated_at_display: str | None = Field(default=None, max_length=200)
    collection_method: str = Field(min_length=1, max_length=200)
    scope: str = Field(min_length=1)
    grade_definition: str | None = None
    identity_note: str | None = None
    data_quality: dict[str, object] | None = None
    prospects: tuple[PFFProspectRow, ...] = Field(min_length=1)

    @field_validator("collected_at")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collected_at must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_board(self) -> "PFFBoardSnapshot":
        """Reject wrong seasons, duplicate identities, and partial/gapped rank ranges."""
        parsed = urlparse(self.source_url)
        if self.source != SOURCE_NAME or parsed.scheme != "https" or parsed.netloc != "www.pff.com":
            raise ValueError("Expected an HTTPS www.pff.com Big Board source")
        if parsed.path != "/draft/big-board" or parse_qs(parsed.query).get("season") != [str(self.draft_year)]:
            raise ValueError("Source URL season must match draft_year")
        ranks = [row.overall_rank for row in self.prospects]
        if sorted(ranks) != list(range(1, len(ranks) + 1)):
            raise ValueError("Ranks must be unique and consecutive starting at 1")
        if len({row.key for row in self.prospects}) != len(self.prospects):
            raise ValueError("Duplicate source identities in snapshot")
        for row in self.prospects:
            if row.position not in POSITION_MAP:
                raise ValueError(f"Unknown PFF position {row.position!r}; add a reviewed mapping")
            canonical_school(row.school)
        return self

    def content_hash(self) -> str:
        """Identify an exact dated snapshot independent of serialization or row order."""
        payload = self.model_dump(mode="json", exclude={"data_quality"})
        payload["prospects"] = sorted(payload["prospects"], key=lambda row: row["overall_rank"])
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        return hashlib.sha256(encoded.encode()).hexdigest()
