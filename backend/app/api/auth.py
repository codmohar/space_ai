"""Authentication endpoints: login, register, and current user profile."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import ApiError
from app.models.auth import Role, User
from app.services.audit import record_audit_log
from app.services.auth.security import (
    create_access_token,
    ensure_default_roles_and_users,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    password: str = Field(..., min_length=4, max_length=255)


class RegisterRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    full_name: str = Field(..., min_length=2, max_length=255)
    password: str = Field(..., min_length=6, max_length=255)


class UserProfileOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfileOut


@router.post("/login", response_model=TokenResponse)
def login(
    req: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ensure_default_roles_and_users(db)
    user = db.execute(
        select(User).where(User.email == req.email.strip().lower())
    ).scalar_one_or_none()

    req_id = getattr(request.state, "request_id", None)
    if user is None or not verify_password(req.password, user.hashed_password):
        record_audit_log(
            db,
            action="auth.login_failed",
            resource_type="user",
            resource_id=req.email.strip().lower(),
            request_id=req_id,
        )
        db.commit()
        raise ApiError("INVALID_CREDENTIALS", "Invalid email or password.", status_code=401)

    if not user.is_active:
        raise ApiError("INACTIVE_USER", "Account is disabled.", status_code=403)

    role_name = user.role.name if user.role else "engineer"
    token = create_access_token(user, role_name)
    record_audit_log(
        db,
        action="auth.login_success",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        request_id=req_id,
        details={"role": role_name},
    )
    db.commit()

    return TokenResponse(
        access_token=token,
        user=UserProfileOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=role_name,
            is_active=user.is_active,
        ),
    )


@router.post("/register", response_model=TokenResponse)
def register(
    req: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ensure_default_roles_and_users(db)
    email = req.email.strip().lower()
    existing = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if existing is not None:
        raise ApiError("EMAIL_EXISTS", "An account with this email already exists.", status_code=409)

    eng_role = db.execute(select(Role).where(Role.name == "engineer")).scalar_one()
    user = User(
        id=uuid.uuid4(),
        email=email,
        full_name=req.full_name.strip(),
        hashed_password=hash_password(req.password),
        role_id=eng_role.id,
        is_active=True,
    )
    db.add(user)
    db.flush()

    req_id = getattr(request.state, "request_id", None)
    record_audit_log(
        db,
        action="auth.register",
        resource_type="user",
        resource_id=str(user.id),
        user_id=user.id,
        request_id=req_id,
        details={"role": "engineer"},
    )
    db.commit()

    token = create_access_token(user, "engineer")
    return TokenResponse(
        access_token=token,
        user=UserProfileOut(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role="engineer",
            is_active=user.is_active,
        ),
    )


@router.get("/me", response_model=UserProfileOut)
def get_me(user: User = Depends(get_current_user)) -> UserProfileOut:
    return UserProfileOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role.name if user.role else "engineer",
        is_active=user.is_active,
    )
