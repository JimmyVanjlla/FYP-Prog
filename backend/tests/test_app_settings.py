"""Unit tests for app/core/config.py's Settings validation — no DB/client
needed, these just construct Settings directly."""
import pytest

from app.core.config import Settings


def test_insecure_default_jwt_secret_rejected_in_production():
    """NFR-Security — the default JWT secret is a literal string in this
    public repo's source; deploying with ENVIRONMENT=production and no
    override would let anyone forge valid tokens for any role."""
    with pytest.raises(ValueError, match="JWT_SECRET must be overridden"):
        Settings(environment="production", jwt_secret="dev-only-insecure-secret-change-me")


def test_overridden_jwt_secret_allowed_in_production():
    Settings(environment="production", jwt_secret="a-real-randomly-generated-secret")


def test_insecure_default_jwt_secret_allowed_in_development():
    # The default environment is "development" — local dev and the test
    # suite itself both run this way, so the insecure default must not be
    # rejected here, only for environment="production".
    Settings(jwt_secret="dev-only-insecure-secret-change-me")


def test_cors_allowed_origins_list_parses_comma_separated_string():
    settings = Settings(cors_allowed_origins="https://a.example.com, https://b.example.com")
    assert settings.cors_allowed_origins_list == ["https://a.example.com", "https://b.example.com"]


def test_cors_allowed_origins_list_empty_by_default():
    assert Settings().cors_allowed_origins_list == []
