from typing import Annotated

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db


DEFAULT_USER_ID = "default"


def normalize_user_id(value: str | None) -> str:
    if not value:
        return DEFAULT_USER_ID

    cleaned = value.strip().lower()

    safe_chars = []

    for char in cleaned:
        if char.isalnum() or char in {"_", "-"}:
            safe_chars.append(char)

    result = "".join(safe_chars).strip("_-")

    return result or DEFAULT_USER_ID


def _expected_profile_pin(user_id: str) -> str:
    settings = get_settings()

    if user_id == "default":
        return settings.profile_default_pin

    if user_id == "second":
        return settings.profile_second_pin

    return ""


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


def get_current_user_id(
    authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
    x_profile_pin: Annotated[str | None, Header(alias="X-Profile-Pin")] = None,
    db: Session = Depends(get_db),
) -> str:
    bearer_token = _extract_bearer_token(authorization)

    if bearer_token:
        from app.services.auth import authenticate_bearer_token

        user_id = authenticate_bearer_token(db, bearer_token)

        if user_id is None:
            raise HTTPException(
                status_code=401,
                detail="Сессия недействительна или истекла.",
            )

        return user_id

    settings = get_settings()

    if not settings.legacy_profile_headers_enabled:
        raise HTTPException(
            status_code=401,
            detail="Требуется вход в аккаунт.",
        )

    user_id = normalize_user_id(x_user_id)

    if not settings.profile_auth_enabled:
        return user_id

    expected_pin = _expected_profile_pin(user_id)

    if not expected_pin:
        raise HTTPException(
            status_code=403,
            detail="Для профиля не настроен PIN.",
        )

    if (x_profile_pin or "").strip() != expected_pin:
        raise HTTPException(
            status_code=401,
            detail="Неверный PIN профиля.",
        )

    return user_id
