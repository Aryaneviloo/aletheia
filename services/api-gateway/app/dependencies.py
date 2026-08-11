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
    """
    Validate the JWT access token and return the authenticated user
    
    Raises Authentication error and Authorization error
    """

    payload = decode_token(token, expected_type="access")

    user_id: str | None = payload.get("sub")
    if not user_id:
        raise AuthenticationError(
            message="TOken is missing object state",
            error_code="token_missing_sub",
        )

    user = db.get(User, user_id)
    if user is None:
        raise AuthenticationError(
            message="User Not Found",
            error_code="user_not_found",
        )

    if not user.is_active:
        raise AuthorizationError(
            message="This account has been deactivated",
            error_code="user_inactive",
        )


def get_current_superuser(
        current_user: User = Depends(get_current_user),
) -> User:
    """
    Used for admin only endpoints
    Builds on get_current_user via Depends() chaining
    """

    if not current_user.is_superuser:
        raise AuthorizationError(
            message="THis action requires superusr privileges",
            error_code="superuser_required"
        )
    return current_user

