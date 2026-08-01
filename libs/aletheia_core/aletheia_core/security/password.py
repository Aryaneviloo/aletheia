"""
aletheia_core.security.password
=================================

Password hashing and verification via bcrypt, called directly.

Usage
-----
    from aletheia_core.security.password import hash_password, verify_password

    # at registration:
    user.hashed_password = hash_password(plain_password)

    # at login:
    if verify_password(plain_password, user.hashed_password):
        ...  # credentials are valid
"""

from __future__ import annotations

import bcrypt
_MAX_PASSWORD_BYTES = 72


def hash_password(plain_password: str) -> str:
    """
    Hash a plaintext password for storage.
    """
    password_bytes = plain_password.encode("utf-8")
    if len(password_bytes) > _MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password must not exceed {_MAX_PASSWORD_BYTES} bytes when UTF-8 encoded "
            f"(got {len(password_bytes)})."
        )
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Check a login attempt's plaintext password against a stored hash.
    """
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except ValueError:
        return False