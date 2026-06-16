"""
Centralized configuration with validation.
All secrets loaded from environment variables via .env — never hardcoded.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Application settings loaded from .env with strict validation."""

    # --- OpenRouter (LLM gateway) ---
    openrouter_api_key: str = Field(
        ...,
        description="OpenRouter API key for LLM access",
        min_length=10,
    )
    openrouter_model: str = Field(
        default="anthropic/claude-sonnet-4",
        description="Model ID from OpenRouter catalog",
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        description="OpenRouter API base URL",
    )

    # --- Sender identity ---
    sender_name: str = Field(
        ...,
        description="Name of the person sending emails",
        min_length=2,
    )
    sender_title: str = Field(
        ...,
        description="Job title of the sender",
        min_length=2,
    )
    company_name: str = Field(
        ...,
        description="Company name used in emails and signatures",
        min_length=2,
    )
    company_description: str = Field(
        ...,
        description="Brief description of the company for LLM context",
        min_length=10,
    )

    # --- Gmail SMTP ---
    gmail_user: str = Field(
        ...,
        description="Gmail address for sending emails",
    )
    gmail_app_password: str = Field(
        ...,
        description="Gmail app password (not regular password)",
        min_length=8,
    )

    # --- Data ---
    excel_file: str = Field(
        default="leads.xlsx",
        description="Path to the leads Excel file",
    )

    # --- Behavior ---
    max_daily_sends: int = Field(
        default=50,
        ge=1,
        le=500,
        description="Maximum emails to send per session",
    )
    max_validation_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max auto-regeneration attempts on validation failure",
    )
    send_delay: int = Field(
        default=2,
        ge=0,
        le=60,
        description="Seconds to wait between email sends",
    )

    # --- Validator limits ---
    tier_3_email_min_words: int = Field(
        default=70,
        ge=20,
        le=500,
        description="Minimum word count for Tier 3 AI-generated emails",
    )
    tier_3_email_max_words: int = Field(
        default=150,
        ge=50,
        le=1000,
        description="Maximum word count for Tier 3 AI-generated emails",
    )
    subject_max_words: int = Field(
        default=8,
        ge=3,
        le=20,
        description="Maximum word count for email subjects",
    )

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


def load_settings() -> Settings:
    """Load and validate settings from environment."""
    return Settings()
