"""Tests for the template service."""

import pytest
from unittest.mock import MagicMock

from services.template_service import TemplateService


def _make_settings(**overrides):
    """Create a mock Settings with identity fields."""
    defaults = {
        "sender_name": "John Smith",
        "sender_title": "Sales Director",
        "company_name": "Acme Corp",
        "company_description": "We help companies hire top talent fast.",
    }
    defaults.update(overrides)
    settings = MagicMock()
    for k, v in defaults.items():
        setattr(settings, k, v)
    return settings


def _make_lead(**overrides):
    """Create a sample lead dict."""
    defaults = {
        "id": "001",
        "contact_name": "Maria Lopez",
        "title_contact": "CTO",
        "company_name": "NovaTech",
        "email": "maria@novatech.io",
        "industry": "Fintech",
        "size": "85",
        "hiring_profile_1": "ML Engineer",
        "hiring_profile_2": "Data Scientist",
    }
    defaults.update(overrides)
    return defaults


class TestRender:
    def test_tier_1_renders_successfully(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead()

        result = service.render(1, lead)

        assert "email_subject" in result
        assert "email_body" in result
        assert "Maria" in result["email_body"]
        assert "John Smith" in result["email_body"]
        assert "Acme Corp" in result["email_body"]

    def test_tier_2_renders_successfully(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead()

        result = service.render(2, lead)

        assert "email_subject" in result
        assert "email_body" in result
        assert "NovaTech" in result["email_body"]

    def test_invalid_tier_raises_error(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead()

        with pytest.raises(FileNotFoundError):
            service.render(99, lead)

    def test_subject_contains_industry(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead(industry="HealthTech")

        result = service.render(1, lead)
        assert "HealthTech" in result["email_subject"]

    def test_first_name_extraction(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead(contact_name="Carlos Rivera")

        result = service.render(1, lead)
        assert "Carlos" in result["email_body"]


class TestBuildVariables:
    def test_all_identity_fields_present(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead()

        variables = service._build_variables(lead)

        assert variables["sender_name"] == "John Smith"
        assert variables["sender_title"] == "Sales Director"
        assert variables["company_name"] == "Acme Corp"
        assert variables["contact_first_name"] == "Maria"
        assert variables["lead_company_name"] == "NovaTech"

    def test_empty_contact_name(self):
        settings = _make_settings()
        service = TemplateService(settings)
        lead = _make_lead(contact_name="")

        variables = service._build_variables(lead)
        assert variables["contact_first_name"] == ""
