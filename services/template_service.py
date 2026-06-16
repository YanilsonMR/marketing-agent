"""
Template Service — loads and renders static email templates for Tier 1/2.

Template format:
    Subject: ...
    ---
    Body text with {placeholders}...
"""

from pathlib import Path

from config.settings import Settings

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"


class TemplateService:
    """Loads .txt templates and renders them with lead + identity data."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def render(self, tier: int, lead: dict) -> dict:
        """Render a template for the given tier. Returns {email_subject, email_body}."""
        template_path = TEMPLATES_DIR / f"tier_{tier}.txt"
        if not template_path.exists():
            raise FileNotFoundError(f"Template not found: {template_path}")

        raw = template_path.read_text(encoding="utf-8")
        subject, body = self._parse_template(raw)

        variables = self._build_variables(lead)
        rendered_subject = subject.format(**variables)
        rendered_body = body.format(**variables)

        return {
            "email_subject": rendered_subject,
            "email_body": rendered_body,
        }

    def _parse_template(self, raw: str) -> tuple[str, str]:
        """Split template into subject and body using '---' separator."""
        parts = raw.split("---", 1)
        if len(parts) != 2:
            raise ValueError("Template must have 'Subject: ...' followed by '---' separator")

        subject_line = parts[0].strip()
        if not subject_line.lower().startswith("subject:"):
            raise ValueError("Template must start with 'Subject: ...'")

        subject = subject_line[len("Subject:"):].strip()
        body = parts[1].strip()

        return subject, body

    def _build_variables(self, lead: dict) -> dict:
        """Merge lead data with identity settings into a single variables dict."""
        contact_name = str(lead.get("contact_name", ""))
        first_name = contact_name.split()[0] if contact_name.strip() else ""

        return {
            # Identity from settings
            "sender_name": self._settings.sender_name,
            "sender_title": self._settings.sender_title,
            "company_name": self._settings.company_name,
            "company_description": self._settings.company_description,
            # Lead data
            "contact_name": contact_name,
            "contact_first_name": first_name,
            "title_contact": str(lead.get("title_contact", "")),
            "lead_company_name": str(lead.get("company_name", "")),
            "industry": str(lead.get("industry", "")),
            "size": str(lead.get("size", "")),
            "hiring_profile_1": str(lead.get("hiring_profile_1", "")),
            "hiring_profile_2": str(lead.get("hiring_profile_2", "")),
        }
