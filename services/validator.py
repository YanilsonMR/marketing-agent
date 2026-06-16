"""
Rules-based content validator for Tier 3 AI-generated emails.

Validates LLM output against quality rules before presenting to the human.
If validation fails, the agent can auto-regenerate (Dark Factory loop).
"""

import re

import emoji

from config.settings import Settings


BANNED_PHRASES = [
    # Espanol
    "espero que este email te encuentre bien",
    "espero que te encuentre bien",
    "queria contactarte",
    "me encontre con tu empresa",
    "en el mundo acelerado de hoy",
    "apalancando",
    "sinergias",
    "estrategico",
    "de clase mundial",
    "innovador",
    "de vanguardia",
    "transformador",
    "revolucionario",
    # Ingles (por si el LLM mezcla idiomas)
    "i hope this email finds you well",
    "i hope this finds you well",
    "i wanted to reach out",
    "i came across your company",
    "in today's fast-paced world",
    "leveraging",
    "synergies",
    "world-class",
    "cutting-edge",
    "transformative",
    "game-changing",
]

TITLE_PATTERNS = [
    r"\bCEO\b", r"\bCTO\b", r"\bCFO\b", r"\bCOO\b", r"\bCMO\b",
    r"\bVP\b", r"\bVice President\b", r"\bVicepresidente\b",
    r"\bDirector\b", r"\bDirectora\b",
    r"\bHead of\b", r"\bJefe de\b", r"\bJefa de\b",
    r"\bChief\b", r"\bFounder\b", r"\bFundador\b", r"\bFundadora\b",
    r"\bCo-Founder\b", r"\bCofundador\b", r"\bCofundadora\b",
    r"\bHR\b", r"\bRRHH\b", r"\bPeople Leader\b",
    r"\bLider de Personas\b",
]


def validate_content(content: dict, settings: Settings) -> list[str]:
    """Validate Tier 3 AI-generated content against all rules.
    Returns list of failure descriptions. Empty list = all passed."""
    failures = []

    email_body = content.get("email_body", "")
    email_subject = content.get("email_subject", "")
    full_text = email_subject + " " + email_body

    # 1. Word count (email body)
    word_count = len(email_body.split())
    if word_count < settings.tier_3_email_min_words:
        failures.append(
            f"word_count_low: {word_count} words (min {settings.tier_3_email_min_words})"
        )
    if word_count > settings.tier_3_email_max_words:
        failures.append(
            f"word_count_high: {word_count} words (max {settings.tier_3_email_max_words})"
        )

    # 2. Subject word count
    subject_words = len(email_subject.split())
    if subject_words > settings.subject_max_words:
        failures.append(
            f"subject_too_long: {subject_words} words (max {settings.subject_max_words})"
        )

    # 3. No exclamation marks
    if "!" in full_text:
        failures.append("exclamation_mark: found '!' in output")

    # 4. No emojis
    if emoji.emoji_count(full_text) > 0:
        failures.append("emoji_found: emojis detected in output")

    # 5. No "P.S." / "P.D."
    if re.search(r"\bP\.?S\.?\b|\bP\.?D\.?\b", email_body, re.IGNORECASE):
        failures.append("ps_pd_found: 'P.S.' o 'P.D.' detectado en el cuerpo del email")

    # 6. Banned phrases
    lower_text = full_text.lower()
    for phrase in BANNED_PHRASES:
        if phrase in lower_text:
            failures.append(f"banned_phrase: '{phrase}'")

    # 7. No job title in email body (excluding the signature block)
    # The signature (sender_name / sender_title / company_name) legitimately
    # contains the sender's title, so we strip it before checking.
    signature_re = (
        re.escape(settings.sender_name)
        + r"\s*\n\s*"
        + re.escape(settings.sender_title)
        + r"\s*\n\s*"
        + re.escape(settings.company_name)
        + r"\s*$"
    )
    body_without_signature = re.sub(signature_re, "", email_body).strip()

    for pattern in TITLE_PATTERNS:
        if re.search(pattern, body_without_signature):
            failures.append(f"job_title_in_body: pattern '{pattern}' found in email")
            break

    # 8. Signature check — sender_name must appear in email body
    if settings.sender_name not in email_body:
        failures.append(
            f"missing_signature: '{settings.sender_name}' not found in email body"
        )

    # 9. No placeholders
    if re.search(r"\[.*?\]|\{\{.*?\}\}", email_body):
        failures.append("placeholder_found: brackets or template vars in email body")

    return failures


def format_failures(failures: list[str]) -> str:
    """Format failure list for display or logging."""
    if not failures:
        return "All rules passed."
    return "Validation failures:\n" + "\n".join(f"  - {f}" for f in failures)
