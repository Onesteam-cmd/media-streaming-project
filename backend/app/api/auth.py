from datetime import datetime

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.schemas import (
    AuthChangePasswordRequest,
    AuthLoginRequest,
    AuthRegisterRequest,
    AuthTokenResponse,
    AuthUserRead,
)
from app.models.tables import AuthSessionTable, UserTable
from app.services.auth import (
    create_session_token,
    hash_password,
    normalize_username,
    hash_token,
    verify_password,
)
from app.services.user_context import get_current_user_id


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_to_read(user: UserTable) -> AuthUserRead:
    return AuthUserRead(
        id=user.id,
        username=user.username,
    )


@router.post("/register", response_model=AuthTokenResponse)
def register(payload: AuthRegisterRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    settings = get_settings()

    if not settings.registration_enabled:
        raise HTTPException(
            status_code=403,
            detail="Регистрация отключена.",
        )

    expected_invite_code = settings.registration_invite_code.strip()

    if expected_invite_code and (payload.invite_code or "").strip() != expected_invite_code:
        raise HTTPException(
            status_code=403,
            detail="Неверный код приглашения.",
        )

    try:
        username = normalize_username(payload.username)
        password_hash = hash_password(payload.password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    existing_user = db.scalars(
        select(UserTable).where(UserTable.id == username)
    ).first()

    if existing_user is not None:
        raise HTTPException(
            status_code=409,
            detail="Пользователь с таким логином уже существует.",
        )

    now = datetime.utcnow()
    user = UserTable(
        id=username,
        username=username,
        password_hash=password_hash,
        created_at=now,
        updated_at=now,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(
        db=db,
        user_id=user.id,
        ttl_days=settings.auth_session_ttl_days,
    )

    return AuthTokenResponse(
        token=token,
        user=_user_to_read(user),
    )


@router.post("/login", response_model=AuthTokenResponse)
def login(payload: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthTokenResponse:
    settings = get_settings()

    try:
        username = normalize_username(payload.username)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user = db.get(UserTable, username)

    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Неверный логин или пароль.",
        )

    token = create_session_token(
        db=db,
        user_id=user.id,
        ttl_days=settings.auth_session_ttl_days,
    )

    return AuthTokenResponse(
        token=token,
        user=_user_to_read(user),
    )


@router.get("/me", response_model=AuthUserRead)
def me(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> AuthUserRead:
    user = db.get(UserTable, current_user_id)

    if user is None:
        return AuthUserRead(
            id=current_user_id,
            username=current_user_id,
        )

    return _user_to_read(user)

def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None

    parts = value.strip().split(" ", 1)

    if len(parts) != 2:
        return None

    scheme, token = parts

    if scheme.lower() != "bearer":
        return None

    return token.strip() or None


@router.post("/logout")
def logout(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    db: Session = Depends(get_db),
) -> dict:
    token = _extract_bearer_token(authorization)

    if token:
        session = db.scalars(
            select(AuthSessionTable).where(AuthSessionTable.token_hash == hash_token(token))
        ).first()

        if session is not None:
            db.delete(session)
            db.commit()

    return {
        "status": "ok",
    }


@router.post("/logout-all")
def logout_all(
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    sessions = db.scalars(
        select(AuthSessionTable).where(AuthSessionTable.user_id == current_user_id)
    ).all()

    count = len(sessions)

    for session in sessions:
        db.delete(session)

    db.commit()

    return {
        "status": "ok",
        "deleted_sessions": count,
    }

@router.post("/change-password")
def change_password(
    payload: AuthChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user_id: str = Depends(get_current_user_id),
) -> dict:
    user = db.get(UserTable, current_user_id)

    if user is None:
        raise HTTPException(
            status_code=404,
            detail="Пользователь не найден.",
        )

    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Текущий пароль неверный.",
        )

    try:
        user.password_hash = hash_password(payload.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    user.updated_at = datetime.utcnow()

    sessions = db.scalars(
        select(AuthSessionTable).where(AuthSessionTable.user_id == current_user_id)
    ).all()

    for session in sessions:
        db.delete(session)

    db.add(user)
    db.commit()

    return {
        "status": "ok",
        "sessions_revoked": len(sessions),
    }

