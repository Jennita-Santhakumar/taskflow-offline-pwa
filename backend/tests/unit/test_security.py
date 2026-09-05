from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_roundtrip():
    h = hash_password("correct-horse-battery-staple")
    assert verify_password("correct-horse-battery-staple", h)
    assert not verify_password("wrong-password", h)


def test_tokens_carry_distinct_jti_even_issued_in_the_same_call():
    # Regression test for the orbit-saas-kit bug: two tokens minted in the same second for the
    # same user must not collide (each mint gets a fresh random jti).
    t1 = create_refresh_token("user-1")
    t2 = create_refresh_token("user-1")
    p1 = decode_token(t1, expected_type="refresh")
    p2 = decode_token(t2, expected_type="refresh")
    assert p1["jti"] != p2["jti"]


def test_decode_token_rejects_wrong_type():
    access = create_access_token("user-1")
    import pytest
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        decode_token(access, expected_type="refresh")
