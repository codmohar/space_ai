"""JWT authentication, PBKDF2 password hashing, and RBAC dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Callable, Optional

from fastapi import Depends, Header
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import ApiError
from app.models.auth import Role, User


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120_000)
    return f"pbkdf2_sha256$120000${salt}${dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algo, iter_s, salt, hex_digest = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), int(iter_s)
        )
        return hmac.compare_digest(dk.hex(), hex_digest)
    except Exception:  # noqa: BLE001
        return False


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def create_access_token(user: User, role_name: str) -> str:
    settings = get_settings()
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "email": user.email,
        "role": role_name,
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
    }
    h_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    p_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{h_b64}.{p_b64}".encode("ascii")
    sig = hmac.new(
        settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    return f"{h_b64}.{p_b64}.{_b64url_encode(sig)}"


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid JWT segments")
        h_b64, p_b64, s_b64 = parts
        signing_input = f"{h_b64}.{p_b64}".encode("ascii")
        expected_sig = hmac.new(
            settings.jwt_secret_key.encode("utf-8"), signing_input, hashlib.sha256
        ).digest()
        actual_sig = _b64url_decode(s_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            raise ValueError("Invalid JWT signature")
        payload = json.loads(_b64url_decode(p_b64).decode("utf-8"))
        if int(payload.get("exp", 0)) < int(time.time()):
            raise ValueError("Token expired")
        return payload
    except Exception as exc:  # noqa: BLE001
        raise ApiError("INVALID_TOKEN", f"Authentication failed: {exc}", status_code=401)


def ensure_default_roles_and_users(db: Session) -> None:
    settings = get_settings()
    roles_by_name: dict[str, Role] = {}
    for role_name, desc in (
        ("admin", "Platform administrator with role, log, and threshold management"),
        ("engineer", "Spacecraft/mission engineer with research, failure-chain, and KG access"),
    ):
        role = db.execute(select(Role).where(Role.name == role_name)).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), name=role_name, description=desc)
            db.add(role)
            db.flush()
        roles_by_name[role_name] = role

    if settings.seed_demo_users:
        existing_user_count = db.execute(select(User.id)).first()
        if existing_user_count is None:
            db.add(
                User(
                    id=uuid.uuid4(),
                    email="admin@missionwise.local",
                    full_name="Flight Ops Admin",
                    hashed_password=hash_password(settings.demo_admin_password),
                    role_id=roles_by_name["admin"].id,
                    is_active=True,
                )
            )
            db.add(
                User(
                    id=uuid.uuid4(),
                    email="engineer@missionwise.local",
                    full_name="Systems Engineer",
                    hashed_password=hash_password(settings.demo_engineer_password),
                    role_id=roles_by_name["engineer"].id,
                    is_active=True,
                )
            )
    db.commit()


def get_optional_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_access_token(token)
    try:
        uid = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise ApiError("INVALID_TOKEN", "Malformed user subject in JWT.", status_code=401) from exc
    user = db.get(User, uid)
    if user is None or not user.is_active:
        raise ApiError("INACTIVE_USER", "User account not found or disabled.", status_code=401)
    return user


def get_current_user(user: Optional[User] = Depends(get_optional_user)) -> User:
    if user is None:
        raise ApiError("AUTHENTICATION_REQUIRED", "Bearer JWT token required.", status_code=401)
    return user


def require_role(*allowed_roles: str) -> Callable[[User], User]:
    def _checker(user: User = Depends(get_current_user)) -> User:
        role_name = user.role.name if user.role else ""
        if role_name not in allowed_roles:
            raise ApiError(
                "FORBIDDEN",
                f"Role '{role_name}' lacks permission. Required: {', '.join(allowed_roles)}.",
                status_code=403,
            )
        return user

    return _checker
