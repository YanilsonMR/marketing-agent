"""
Email Service — sends plain-text emails via Gmail SMTP.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config.settings import Settings


class EmailService:
    """Sends emails via Gmail SMTP using app password."""

    def __init__(self, settings: Settings) -> None:
        self._gmail_user = settings.gmail_user
        self._gmail_password = settings.gmail_app_password
        self._from_name = settings.sender_name

    def send(self, to_email: str, subject: str, body: str) -> bool:
        """Send a plain-text email. Returns True on success, False on failure."""
        msg = MIMEMultipart()
        msg["From"] = f"{self._from_name} <{self._gmail_user}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(self._gmail_user, self._gmail_password)
                server.sendmail(self._gmail_user, to_email, msg.as_string())
            return True
        except smtplib.SMTPException as e:
            print(f"  Error al enviar email: {e}")
            return False
