"""
Prompt Builder — constructs system + user prompts for Tier 3 AI generation.

Tier 1/2 use static templates (TemplateService), so this module is only
called for Tier 3 leads that need AI-generated content.
"""

from pathlib import Path

from config.settings import Settings

PROMPTS_DIR = Path(__file__).parent


def _load_md(filename: str) -> str:
    """Load a markdown file from the prompts directory."""
    return (PROMPTS_DIR / filename).read_text(encoding="utf-8")


def build_prompt(lead: dict, settings: Settings) -> tuple[str, str]:
    """Build system + user prompts for a Tier 3 lead.

    Returns (system_prompt, user_prompt).
    """
    # Load and inject identity into context
    context = _load_md("context.md")
    context = context.format(
        sender_name=settings.sender_name,
        sender_title=settings.sender_title,
        company_name=settings.company_name,
        company_description=settings.company_description,
    )

    # Load tier 3 strategy
    tier_strategy = _load_md("tier_3.md")
    tier_strategy = tier_strategy.replace("{sender_name}", settings.sender_name)
    tier_strategy = tier_strategy.replace("{sender_title}", settings.sender_title)
    tier_strategy = tier_strategy.replace("{company_name}", settings.company_name)

    # Load and fill lead data
    intent_template = _load_md("intent.md")
    intent = intent_template
    for key, value in lead.items():
        intent = intent.replace(f"{{{{{key}}}}}", str(value))

    system_prompt = context + "\n\n" + tier_strategy
    user_prompt = intent

    return system_prompt, user_prompt
