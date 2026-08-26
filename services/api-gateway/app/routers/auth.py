"""
api_gateway.app.routers.auth
================================

Registration, login, token refresh, and current user endpoint

Refresh token rotation
----------------------
On every auth/refresh call, the old refresh token is revoked and a
brand new one is issued. A stolen refresh token can therefore only 
be used once

Token Storage
--------------
Access tokens are not stored they are stateless JWTs valid for their
lifetime with no way to revoke early
"""

from __future__ import annotations
import hashlib
import datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import RefreshToken, User
from aletheia_core.exceptions import AuthenticationError, ConflictError

from aletheia_core.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    TokenPair,
    UserCreate,
    UserRead,
)
from aletheia_core.security.jwt import create_access_token, create_refresh_token, decode_token
from aletheia_core.security.password import hash_password, verify_password
from app.dependencies import get_current_user


router = APIRouter(prefix="/auth", tags = ["auth"])

def hash_token(raw_token: str) -> str:
    """
    SHA-256 hash of a refresh token for storage
    SHA-256 is fast and sufficient for lookup process
    """
    return hashlib.sha256(raw_token.encode()).hexdigest()

@router.post("/register", response_model=UserRead,
             status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> User:
    """
    Create a new user account
    Returns 409 if the email is already registered
    """
    existing = db.query(User).filter(User.email == payload.email).first()
    if existing: 
        raise ConcflictError(
            message="An account eith this email already exists",
            error_code="email_already_registered",
        )

    user = User(
        email = payload.email,
        hashed_password = hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenPair)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenPair:
    """
    Authenticate with email and password, receieve an access/refresh
    token pair.
    """
    user = db.query(User).filter(User.email == payload.email).first()

    #verify password on a fake hash even when the user doesnt exists
    # prevents timing attacks 
    if not user or not verify_password(payload.password,
                                       user.hashed_password):
        raise AuthenticationError(
            message="Invalid email or password",
            error_code="invalid_credentials",
        )

    access_token = create_access_token(user_id=str(user.id))
    refresh_token = create_refresh_token(user_id=str(user.id))

    # Store the hash of teh refresh token never the raw token
    db.add(RefreshToken(
        user_id = user.id,
        token_hash = hash_token(refresh_token),
        expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=14),
    ))
    db.commit()

    return TokenPair(access_token=access_token, refresh_token=refresh_token)

@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenPair:
    """
    Exchange a valid refresh token for a new token pair.
    Using a revoked token returns 401
    """
    try:
        token_payload = decode_token(payload.refresh_token,
                                     expected_type="refresh")
    except AuthenticationError:
        raise

    token_hash = hash_token(payload.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash
    ).first()

    if not stored or stored.revoked_at is not None:
        raise AuthenticationError(
            message="Refresh token is invalid or has been revoked",
            error_code="refresh_token_invallid"
        )

    if stored.expires_at < datetime.datetime.now(datetime.timezone.utc):
        raise AuthenticationError(
            message="Refresh token has expired",
            error_code="refresh_token_expired",
        )

    stored.revoked_at = datetime.datetime.now(datetime.timezone.utc)

    user_id = token_payload["sub"]
    new_access = create_access_token(user_id=user_id)
    new_refresh = create_refresh_token(user_id=user_id)

    
    db.add(RefreshToken(
        user_id=stored.user_id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.datetime.now(datetime.timezone.utc)
                   + datetime.timedelta(days=14),
    ))
    db.commit()

    return TokenPair(access_token=new_access, refresh_token=new_refresh)

@router.post("/logout")
def logout(
    payload: RefreshRequest,
    db: Session = Depends(get_db),
    current_user : User = Depends(get_current_user),
) -> dict:
    """
    Revoke a specific refresh token and requires a valid
    access token
    """

    token_hash = hash_token(payload.refresh_token)
    stored = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == current_user.id,
    ).first()

    if stored and stored.revoked_at is None:
        stored.revoked_at = datetime.datetime.now(datetime.timezone.utc)
        db.commit()


    return {"message":  "Logged out successfully."}

@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user