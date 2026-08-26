"""
api_gateway.app.dependencies
================================

Reusable FASTApi dependencies shared across all routers
The dependecncy chain for a protected route:
    oath2_scheme extracts the bearer token from authorization
      ->decode tokem verifies the JWT 
        -> db query loads the real user 
          -> route handler reeives a typed User object
          
"""

from __future__ import annotations
import uuid as uuid_lib
from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from aletheia_core.db.base import get_db
from aletheia_core.db.models import User
from aletheia_core.exceptions import AuthenticationError, AuthorizationError
from aletheia_core.security.jwt import decode_token

#Oathpas.. extracts the token string from authorization header and
# return it as a plain string
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    payload = decode_token(token, expected_type="access")

    user_id_str: str | None = payload.get("sub")
    if not user_id_str:
        raise AuthenticationError(
            message="Token is missing subject claim.",
            error_code="token_missing_sub",
        )

    try:
        user_id = uuid_lib.UUID(user_id_str)
    except ValueError:
        raise AuthenticationError(
            message="Token subject is not a valid UUID.",
            error_code="token_invalid_sub",
        )

    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError(
            message="User not found.",
            error_code="user_not_found",
        )

    if not user.is_active:
        raise AuthorizationError(
            message="This account has been deactivated.",
            error_code="user_inactive",
        )

    return user