"""Public reference-data endpoints for FBS college football programs."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CollegeRecord
from app.db.session import get_db

router = APIRouter(prefix="/api/colleges", tags=["colleges"])


@router.get("")
def list_colleges(session: Session = Depends(get_db)) -> list[dict[str, object]]:
    """Return FBS programs ordered by conference and school name."""
    colleges = session.scalars(
        select(CollegeRecord).order_by(CollegeRecord.conference, CollegeRecord.name)
    ).all()
    return [
        {
            "id": college.id,
            "name": college.name,
            "abbreviation": college.abbreviation,
            "conference": college.conference,
            "division": college.division,
            "logo_url": college.logo_url,
            "official_url": college.official_url,
        }
        for college in colleges
    ]