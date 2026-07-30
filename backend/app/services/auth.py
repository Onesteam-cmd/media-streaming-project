from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.tables import AuthSessionTable, UserTable
from app.services.user_context import normalize_user_id


PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
PASSWORD_HASH_ITERATIONS = 260_000


def normalize_username(value: str) -> str:
    username = normalize_user_id(value)

    if len(username) < 3:
        raise ValueError("Логин должен быть не короче 3 символов.")

    if len(username) > 64:
        raise ValueError("Логин должен быть не длиннее 64 символов.")

    return username


def hash_password(password: str) -> str:
    if len(password) < 6:
        raise ValueError("Пароль должен быть не короче 6 символов.")

    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_HASH_ITERATIONS,
    )

    return "$".join(
        [
            PASSWORD_HASH_ALGORITHM,
            str(PASSWORD_HASH_ITERATIONS),
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = stored_hash.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected_digest = base64.urlsafe_b64decode(digest_text.encode("ascii"))
    except Exception:
        return False

    if algorithm != PASSWORD_HASH_ALGORITHM:
        return False

    actual_digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
    )

    return hmac.compare_digest(actual_digest, expected_digest)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session_token(db: Session, user_id: str, ttl_days: int) -> str:
    token = secrets.token_urlsafe(32)
    now = datetime.utcnow()

    session = AuthSessionTable(
        user_id=user_id,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + timedelta(days=max(1, ttl_days)),
    )

    db.add(session)
    db.commit()

    return token


def authenticate_bearer_token(db: Session, token: str) -> str | None:
    token = token.strip()

    if not token:
        return None

    now = datetime.utcnow()

    session = db.scalars(
        select(AuthSessionTable)
        .where(AuthSessionTable.token_hash == hash_token(token))
        .where(AuthSessionTable.expires_at > now)
    ).first()

    if session is None:
        return None

    user = db.get(UserTable, session.user_id)

    if user is None:
        return None

    session.last_used_at = now
    db.commit()

    return user.id
