"""
CSV quality logger — tracks all actions taken on leads.
"""

import csv
from datetime import datetime
from pathlib import Path

LOG_FILE = "quality_log.csv"

FIELDS = [
    "timestamp",
    "lead_id",
    "contact_name",
    "company",
    "tier",
    "icp_rank",
    "word_count_email",
    "action",
    "rejection_reason",
    "regenerated",
    "feedback",
    "validation_passed",
    "validation_failures",
    "attempts",
]


def _ensure_file():
    """Create CSV with headers if it doesn't exist."""
    if not Path(LOG_FILE).exists():
        with open(LOG_FILE, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()


def log_event(
    lead_id: str = "",
    contact_name: str = "",
    company: str = "",
    tier: str = "",
    icp_rank: str = "",
    word_count_email: int = 0,
    action: str = "",
    rejection_reason: str = "",
    regenerated: str = "no",
    feedback: str = "",
    validation_passed: str = "n/a",
    validation_failures: str = "",
    attempts: int = 1,
):
    """Append one row to the quality log."""
    _ensure_file()

    row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "lead_id": lead_id,
        "contact_name": contact_name,
        "company": company,
        "tier": tier,
        "icp_rank": icp_rank,
        "word_count_email": word_count_email,
        "action": action,
        "rejection_reason": rejection_reason,
        "regenerated": regenerated,
        "feedback": feedback,
        "validation_passed": validation_passed,
        "validation_failures": validation_failures,
        "attempts": attempts,
    }

    with open(LOG_FILE, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writerow(row)
