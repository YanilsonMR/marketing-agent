"""Tests for configuration settings validation."""

import os
import pytest
from unittest.mock import patch

from config.settings import Settings


VALID_ENV = {
    "OPENROUTER_API_KEY": "sk-or-v1-test-key-that-is-long-enough",
    "OPENROUTER_MODEL": "anthropic/claude-sonnet-4",
    "OPENROUTER_BASE_URL": "https://openrouter.ai/api/v1",
    "SENDER_NAME": "Test User",
    "SENDER_TITLE": "Test Title",
    "COMPANY_NAME": "Test Company",
    "COMPANY_DESCRIPTION": "A company that does testing of things well.",
    "GMAIL_USER": "test@gmail.com",
    "GMAIL_APP_PASSWORD": "test-password-here",
    "EXCEL_FILE": "leads.xlsx",
    "MAX_DAILY_SENDS": "50",
    "MAX_VALIDATION_RETRIES": "3",
    "SEND_DELAY": "2",
    "TIER_3_EMAIL_MIN_WORDS": "80",
    "TIER_3_EMAIL_MAX_WORDS": "150",
    "SUBJECT_MAX_WORDS": "8",
}


class TestSettingsValidation:
    @patch.dict(os.environ, VALID_ENV, clear=False)
    def test_valid_settings_load(self):
        settings = Settings()
        assert settings.sender_name == "Test User"
        assert settings.company_name == "Test Company"
        assert settings.openrouter_model == "anthropic/claude-sonnet-4"

    @patch.dict(os.environ, {**VALID_ENV, "OPENROUTER_API_KEY": ""}, clear=False)
    def test_missing_api_key_fails(self):
        with pytest.raises(Exception):
            Settings()

    @patch.dict(os.environ, {**VALID_ENV, "SENDER_NAME": ""}, clear=False)
    def test_missing_sender_name_fails(self):
        with pytest.raises(Exception):
            Settings()

    @patch.dict(os.environ, VALID_ENV, clear=False)
    def test_default_values(self):
        settings = Settings()
        assert settings.max_daily_sends == 50
        assert settings.max_validation_retries == 3
        assert settings.send_delay == 2
        assert settings.tier_3_email_min_words == 80
        assert settings.tier_3_email_max_words == 150
        assert settings.subject_max_words == 8

    @patch.dict(os.environ, {**VALID_ENV, "MAX_DAILY_SENDS": "100"}, clear=False)
    def test_custom_max_daily_sends(self):
        settings = Settings()
        assert settings.max_daily_sends == 100

    @patch.dict(os.environ, {**VALID_ENV, "TIER_3_EMAIL_MIN_WORDS": "60"}, clear=False)
    def test_custom_validator_limits(self):
        settings = Settings()
        assert settings.tier_3_email_min_words == 60
