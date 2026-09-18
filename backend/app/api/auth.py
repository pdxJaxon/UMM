"""Authentication routes for login and registration."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, validate_password, verify_password
from app.core.auth import get_current_user
from app.db.models import TeamRecord, UserRecord
from app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """Payload used to create a new user account."""

    email: EmailStr
    password: str = Field(max_length=256)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    favorite_team_id: str = Field(min_length=1, max_length=64)


class LoginRequest(BaseModel):
    """Payload used to authenticate an existing user."""

    email: EmailStr
    password: str = Field(max_length=256)


class FavoriteTeamRequest(BaseModel):
    """Payload used to change the signed-in user's preferred team."""

    favorite_team_id: str = Field(min_length=1, max_length=64)


@router.post("/register", status_code=201)
def register_account(payload: RegisterRequest, session: Session = Depends(get_db)) -> dict[str, str | None]:
    """Create a persistent user profile and return a bearer access token."""
    normalized_email = str(payload.email).strip().lower()
    try:
        validate_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if session.get(TeamRecord, payload.favorite_team_id) is None:
        raise HTTPException(status_code=400, detail="Favorite team was not found")
    user = UserRecord(
        id=f"user-{session.query(UserRecord).count() + 1}",
        email=normalized_email,
        password_hash=hash_password(payload.password),
        first_name=payload.first_name.strip(),
        last_name=payload.last_name.strip(),
        favorite_team_id=payload.favorite_team_id,
    )
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="User already exists") from exc

    return {
        "id": user.id,
        "email": user.email,
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "favorite_team_id": user.favorite_team_id,
    }


@router.post("/login")
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> dict[str, str | None]:
    """Authenticate a persistent user and return a signed bearer token."""
    statement = select(UserRecord).where(UserRecord.email == str(payload.email).strip().lower())
    user = session.scalar(statement)
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return {
        "id": user.id,
        "email": user.email,
        "access_token": create_access_token(user.id),
        "token_type": "bearer",
        "favorite_team_id": user.favorite_team_id,
    }


@router.patch("/me/favorite-team")
def update_favorite_team(
    payload: FavoriteTeamRequest,
    current_user: UserRecord = Depends(get_current_user),
    session: Session = Depends(get_db),
) -> dict[str, str]:
    """Update the preferred team for the authenticated account."""
    if session.get(TeamRecord, payload.favorite_team_id) is None:
        raise HTTPException(status_code=400, detail="Favorite team was not found")

    current_user.favorite_team_id = payload.favorite_team_id
    session.commit()
    return {"favorite_team_id": current_user.favorite_team_id}
