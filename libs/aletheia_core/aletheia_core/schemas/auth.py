"""
aletheia_core.schemas.auth
=============================

Request/response shapes for authentication — registration, login,
token refresh. Used by the auth router (Phase 7), not by the ORM
layer directly.
Usage
-----
    # Building a response from a real ORM User object:
    user_out = UserRead.model_validate(user)  # reads matching attributes off `user`, ignores the rest

    # Registration request body:
    async def register(payload: UserCreate): ...
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserCreate(BaseModel):
    """Registration request body."""

    email: EmailStr
    #Catching an oversized password
    #much better than letting it travel all the way down to bcrypt
    password: str = Field(min_length=8, max_length=72)


class UserRead(BaseModel):
    """
    User data safe to return in an API response.
    """

    id: uuid.UUID
    email: EmailStr
    is_active: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr
    password: str


class TokenPair(BaseModel):
    """
    Response returned on successful login or token refresh.
    """
    access_token: str
    refresh_token: str
    token_type: Literal["bearer"] = "bearer"


class RefreshRequest(BaseModel):
    """Request body for exchanging a refresh token for a new access token."""

    refresh_token: str