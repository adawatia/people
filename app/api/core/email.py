import asyncio
import logging
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path

from core.settings import get_settings

logger = logging.getLogger("hrms")


class EmailService:
    def __init__(self):
        self.settings = get_settings()

    def _create_message(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> MIMEMultipart:
        # Outer multipart/related container for HTML and inline images (RFC 2387)
        msg = MIMEMultipart("related")
        msg["Subject"] = subject
        from_email = self.settings.mail_from or self.settings.mail_username
        msg["From"] = formataddr(("Datlab People", from_email))
        msg["To"] = to_email

        # Inner multipart/alternative container (plain text fallback + rich HTML)
        msg_alt = MIMEMultipart("alternative")
        part_text = MIMEText(text_body, "plain", "utf-8")
        part_html = MIMEText(html_body, "html", "utf-8")
        msg_alt.attach(part_text)
        msg_alt.attach(part_html)
        msg.attach(msg_alt)

        # Attach inline logo PNG (CID: bsl-logo) for offline & universal email client rendering
        logo_path = Path(__file__).resolve().parent.parent / "templates" / "email" / "logo.png"
        if logo_path.exists():
            try:
                logo_data = logo_path.read_bytes()
                logo_img = MIMEImage(logo_data, "png")
                logo_img.add_header("Content-ID", "<bsl-logo>")
                logo_img.add_header("Content-Disposition", "inline", filename="logo.png")
                msg.attach(logo_img)
            except Exception as e:
                logger.warning("Failed to attach inline logo to email: %s", e)

        return msg

    def _send_smtp_sync(self, msg: MIMEMultipart, to_email: str) -> None:
        host = self.settings.mail_server
        port = self.settings.mail_port
        username = self.settings.mail_username
        password = self.settings.mail_password

        if not host:
            logger.warning("SMTP configuration incomplete; email to %s skipped (host missing)", to_email)
            return

        # Choose the correct connection class based on MAIL_SSL_TLS
        smtp_class = smtplib.SMTP_SSL if self.settings.mail_ssl_tls else smtplib.SMTP
        
        with smtp_class(host=host, port=port, timeout=15) as server:
            server.ehlo()
            if self.settings.mail_starttls and not self.settings.mail_ssl_tls:
                server.starttls()
                server.ehlo()
            
            if self.settings.use_credentials and username and password:
                server.login(username, password)
            
            server.send_message(msg)

    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None:
        """
        Sends an email asynchronously via threadpool to prevent blocking the event loop.
        """
        msg = self._create_message(to_email, subject, html_body, text_body)
        try:
            await asyncio.to_thread(self._send_smtp_sync, msg, to_email)
            logger.info("Email '%s' sent successfully to %s", subject, to_email)
        except Exception as exc:
            # Never log sensitive data or credentials
            logger.error("Failed to send email to %s: %s", to_email, str(exc))

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        username: str,
        reset_url: str,
    ) -> None:
        subject = "Reset your HRMS password"

        base_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
        frontend_base = (self.settings.frontend_url or "http://localhost:3000").rstrip("/")
        
        text_template = (base_dir / "password_reset.txt").read_text(encoding="utf-8")
        text_body = text_template.format(user_name=user_name, username=username, reset_url=reset_url, to_email=to_email)

        html_template = (base_dir / "password_reset.html").read_text(encoding="utf-8")
        html_body = html_template.format(user_name=user_name, username=username, reset_url=reset_url, to_email=to_email, frontend_url=frontend_base)

        await self.send_email(to_email, subject, html_body, text_body)

    async def send_user_invitation_email(
        self,
        to_email: str,
        user_name: str,
        username: str,
        role_name: str,
        invite_url: str,
    ) -> None:
        subject = "You're invited to HRMS"

        base_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
        frontend_base = (self.settings.frontend_url or "http://localhost:3000").rstrip("/")
        formatted_role = role_name.replace("_", " ") if role_name else "User"
        
        text_template = (base_dir / "user_invitation.txt").read_text(encoding="utf-8")
        text_body = text_template.format(user_name=user_name, username=username, role_name=formatted_role, invite_url=invite_url, to_email=to_email)

        html_template = (base_dir / "user_invitation.html").read_text(encoding="utf-8")
        html_body = html_template.format(user_name=user_name, username=username, role_name=formatted_role, invite_url=invite_url, to_email=to_email, frontend_url=frontend_base)

        await self.send_email(to_email, subject, html_body, text_body)

    async def send_verification_email(
        self,
        to_email: str,
        user_name: str,
        verify_url: str,
    ) -> None:
        subject = "Verify your email address for HRMS"

        base_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
        frontend_base = (self.settings.frontend_url or "http://localhost:3000").rstrip("/")
        
        text_template = (base_dir / "email_verification.txt").read_text(encoding="utf-8")
        text_body = text_template.format(user_name=user_name, verify_url=verify_url, to_email=to_email)

        html_template = (base_dir / "email_verification.html").read_text(encoding="utf-8")
        html_body = html_template.format(user_name=user_name, verify_url=verify_url, to_email=to_email, frontend_url=frontend_base)

        await self.send_email(to_email, subject, html_body, text_body)

    async def send_email_changed_alert(
        self,
        old_email: str,
        new_email: str,
    ) -> None:
        subject = "Security Alert: Email Address Changed"

        base_dir = Path(__file__).resolve().parent.parent / "templates" / "email"
        frontend_base = (self.settings.frontend_url or "http://localhost:3000").rstrip("/")
        
        text_template = (base_dir / "email_changed_alert.txt").read_text(encoding="utf-8")
        text_body = text_template.format(old_email=old_email, new_email=new_email)

        html_template = (base_dir / "email_changed_alert.html").read_text(encoding="utf-8")
        html_body = html_template.format(old_email=old_email, new_email=new_email, frontend_url=frontend_base)

        await self.send_email(old_email, subject, html_body, text_body)

email_service = EmailService()


def get_email_service() -> EmailService:
    return email_service
