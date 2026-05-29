from app.auth.password import hash_password, verify_password, validate_password_strength
import pytest


def test_hash_is_not_plaintext():
    hashed = hash_password("SuperSecret123!")
    assert hashed != "SuperSecret123!"
    assert hashed.startswith("$2b$")


def test_correct_password_verifies():
    hashed = hash_password("SuperSecret123!")
    assert verify_password("SuperSecret123!", hashed) is True


def test_wrong_password_fails():
    hashed = hash_password("SuperSecret123!")
    assert verify_password("WrongPassword!", hashed) is False


def test_short_password_raises():
    with pytest.raises(ValueError, match="12 characters"):
        validate_password_strength("Short1!")


def test_no_uppercase_raises():
    with pytest.raises(ValueError, match="uppercase"):
        validate_password_strength("alllowercase123!")


def test_no_digit_raises():
    with pytest.raises(ValueError, match="digit"):
        validate_password_strength("AllUppercaseNoDigit!")


def test_valid_password_does_not_raise():
    validate_password_strength("ValidPass123!")  # should not raise
