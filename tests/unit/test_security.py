

from __future__ import annotations

import pytest
from aletheia_core.security.password import hash_password, verify_password
from aletheia_core.security.jwt import create_access_token, create_refresh_token, decode_token
from aletheia_core.exceptions import AuthenticationError


def test_password_hash_not_plaintext():
    h = hash_password("mypassword")
    assert h != "mypassword"
    assert h.startswith("$2b$")


def test_password_verify_correct():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h) is True


def test_password_verify_wrong():
    h = hash_password("mypassword")
    assert verify_password("wrongpassword", h) is False


def test_password_same_input_different_hashes():
    """bcrypt salting — same password, different hashes."""
    h1 = hash_password("mypassword")
    h2 = hash_password("mypassword")
    assert h1 != h2


def test_access_token_decode():
    token = create_access_token(user_id="test-user-id")
    payload = decode_token(token, expected_type="access")
    assert payload["sub"] == "test-user-id"
    assert payload["type"] == "access"


def test_refresh_token_decode():
    token = create_refresh_token(user_id="test-user-id")
    payload = decode_token(token, expected_type="refresh")
    assert payload["type"] == "refresh"


def test_wrong_token_type_rejected():
    refresh = create_refresh_token(user_id="test-user-id")
    with pytest.raises(AuthenticationError) as exc_info:
        decode_token(refresh, expected_type="access")
    assert exc_info.value.error_code == "token_wrong_type"


def test_invalid_token_rejected():
    with pytest.raises(AuthenticationError) as exc_info:
        decode_token("not.a.real.token", expected_type="access")
    assert exc_info.value.error_code == "token_invalid"