"""Tests for the rules-based content validator."""

import pytest
from unittest.mock import MagicMock

from services.validator import validate_content


def _make_settings(**overrides):
    """Create a mock Settings object with sensible defaults."""
    defaults = {
        "tier_3_email_min_words": 80,
        "tier_3_email_max_words": 150,
        "subject_max_words": 8,
        "sender_name": "Test User",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_content(subject="Short subject", body=None):
    """Create a valid content dict with enough words."""
    if body is None:
        # Generate a body with ~100 words that includes the signature
        words = " ".join(f"word{i}" for i in range(95))
        body = f"{words}\n\nTest User\nTitle\nCompany"
    return {"email_subject": subject, "email_body": body}


class TestWordCount:
    def test_body_too_short(self):
        settings = _make_settings()
        content = _make_content(body="Only five words here today.\n\nTest User\nTitle\nCompany")
        failures = validate_content(content, settings)
        assert any("word_count_low" in f for f in failures)

    def test_body_too_long(self):
        settings = _make_settings(tier_3_email_max_words=10)
        content = _make_content()
        failures = validate_content(content, settings)
        assert any("word_count_high" in f for f in failures)

    def test_body_within_range(self):
        settings = _make_settings()
        content = _make_content()
        failures = validate_content(content, settings)
        assert not any("word_count" in f for f in failures)


class TestSubjectLength:
    def test_subject_too_long(self):
        settings = _make_settings(subject_max_words=3)
        content = _make_content(subject="This is a very long subject line")
        failures = validate_content(content, settings)
        assert any("subject_too_long" in f for f in failures)

    def test_subject_within_limit(self):
        settings = _make_settings()
        content = _make_content(subject="Short subject")
        failures = validate_content(content, settings)
        assert not any("subject_too_long" in f for f in failures)


class TestExclamationMarks:
    def test_exclamation_in_body(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(95))
        body = f"Great news! {words}\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("exclamation_mark" in f for f in failures)

    def test_exclamation_in_subject(self):
        settings = _make_settings()
        content = _make_content(subject="Great news!")
        failures = validate_content(content, settings)
        assert any("exclamation_mark" in f for f in failures)


class TestBannedPhrases:
    def test_banned_phrase_detected(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(90))
        body = f"I hope this email finds you well. {words}\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("banned_phrase" in f for f in failures)

    def test_clean_content_passes(self):
        settings = _make_settings()
        content = _make_content()
        failures = validate_content(content, settings)
        assert not any("banned_phrase" in f for f in failures)


class TestSignature:
    def test_missing_signature(self):
        settings = _make_settings(sender_name="Jane Doe")
        words = " ".join(f"word{i}" for i in range(95))
        body = f"{words}\n\nSomeone Else\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("missing_signature" in f for f in failures)

    def test_signature_present(self):
        settings = _make_settings()
        content = _make_content()
        failures = validate_content(content, settings)
        assert not any("missing_signature" in f for f in failures)


class TestPlaceholders:
    def test_bracket_placeholders(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(90))
        body = f"Hello [Name], {words}\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("placeholder_found" in f for f in failures)

    def test_template_var_placeholders(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(90))
        body = f"Hello {{{{name}}}}, {words}\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("placeholder_found" in f for f in failures)


class TestJobTitles:
    def test_job_title_in_body(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(90))
        body = f"As a CEO you know {words}\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("job_title_in_body" in f for f in failures)


class TestPS:
    def test_ps_detected(self):
        settings = _make_settings()
        words = " ".join(f"word{i}" for i in range(90))
        body = f"{words}\n\nP.S. One more thing\n\nTest User\nTitle\nCompany"
        content = _make_content(body=body)
        failures = validate_content(content, settings)
        assert any("ps_pd_found" in f for f in failures)


class TestValidContent:
    def test_fully_valid_content(self):
        settings = _make_settings()
        content = _make_content()
        failures = validate_content(content, settings)
        assert failures == []
