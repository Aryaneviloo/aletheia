"""
aletheia_core.security.py
==============================

Access and refresh tokens via Pyjwt
Access tokens are short lived and sent with every authenticated request
if one leaks the exposure window is small by design and it self expires

Refresh tokens are long lived but used only to mint a new access token;
their HASH is stored in the RefreshToken table
Usage
-----
    from aletheia_core.security.jwt import create_access_token, decode_token

    token = create_access_token(user_id=str(user.id))
    payload = decode_token(token, expected_type="access")  # raises AuthenticationError if invalid/expired/wrong type
"""

from __future__ import annotations
import datetime

import uuid
import jwt
from typing import Any, Literal

from aletheia_core.config import get_settings
from aletheia_core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh"]

def create_token(*, user_id: str, token_type: TokenType, expires_delta: datetime.timedelta) -> str:
    """
    Shared internals for both token types
    """
    settings = get_settings()
    now = datetime.datetime.now(datetime.timezone.utc)

    payload: dict[str, Any] = {
        "sub" : user_id,
        "type": token_type,
        "iat" : now,
        "exp" : now + expires_delta,
        "jti" : str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def create_access_token(user_id: str) -> str:
    """ Issue a short lived access token for an authenticated user"""
    settings = get_settings()
    return create_token(
        user_id=user_id,
        token_type="access",
        expires_delta=datetime.timedelta(minutes=settings.access_token_expire_minutes),
    )

def create_refresh_token(user_id: str) -> str:
    """
    Issue a long lived refresh token, only creates the JWT itself it 
    doesn't know about the database
    """
    settings = get_settings()
    return create_token(
        user_id=user_id,
        token_type="refresh",
        expires_delta=datetime.timedelta(days=settings.refresh_token_expire_days),
    )

def decode_token(token: str, *, expected_type: TokenType) -> dict[str, Any]:
    """
    Verify a token's signature and expiry and confirm it's the type
    the caller actually expects
    Raises Autehntication error
    """
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as e:
        raise AuthenticationError(message="Token has expired", error_code="token_expired") from e 
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(message="Token is invalid", error_code="token_invalid") from e

    if payload.get("type") != expected_type:
        raise AuthenticationError(
            message=f"Expected a {expected_type}token, got {payload.get('type')}",
            error_code="token_wrong_type",
        )

    return payload