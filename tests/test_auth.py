"""Test auth utilities."""

from app.services.auth import create_access_token, decode_token, hash_password, verify_password


def test_password_hashing():
    plain = "test-password-123"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)
    assert not verify_password("wrong", hashed)


def test_jwt_token():
    token = create_access_token({"sub": "user@example.com"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "user@example.com"


def test_jwt_token_with_superuser():
    token = create_access_token({"sub": "admin@example.com", "is_superuser": True})
    payload = decode_token(token)
    assert payload is not None
    assert payload["is_superuser"] is True


def test_invalid_token():
    payload = decode_token("invalid.token.here")
    assert payload is None


def test_empty_token():
    payload = decode_token("")
    assert payload is None
