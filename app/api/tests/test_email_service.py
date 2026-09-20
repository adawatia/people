from unittest.mock import MagicMock, patch

import pytest

from core.email import EmailService
from core.settings import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        mail_server="smtppro.zoho.com",
        mail_port=587,
        mail_username="notifications@example.com",
        mail_password="test-secure-password",
        mail_from="notifications@example.com",
        mail_starttls=True,
        mail_ssl_tls=False,
        use_credentials=True,
        frontend_url="http://localhost:5173",
    )


@pytest.mark.asyncio
async def test_email_service_creates_mime_message_properly(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    msg = service._create_message(
        to_email="recipient@example.com",
        subject="Test Subject",
        html_body="<p>Test HTML</p>",
        text_body="Test Plain Text",
    )

    assert msg["Subject"] == "Test Subject"
    assert msg["To"] == "recipient@example.com"
    assert "notifications@example.com" in msg["From"]
    assert msg.get_content_type() == "multipart/related"

    payload = msg.get_payload()
    assert len(payload) >= 1
    alt_part = payload[0]
    assert alt_part.get_content_type() == "multipart/alternative"
    alt_payload = alt_part.get_payload()
    assert alt_payload[0].get_content_type() == "text/plain"
    assert alt_payload[1].get_content_type() == "text/html"

    if len(payload) > 1:
        img_part = payload[1]
        assert img_part.get_content_type() == "image/png"
        assert img_part["Content-ID"] == "<bsl-logo>"


@pytest.mark.asyncio
async def test_send_smtp_sync_uses_starttls_and_credentials(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    msg = service._create_message(
        to_email="recipient@example.com",
        subject="Test",
        html_body="<p>Body</p>",
        text_body="Body",
    )

    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        service._send_smtp_sync(msg, "recipient@example.com")

        mock_smtp.assert_called_once_with(host="smtppro.zoho.com", port=587, timeout=15)
        mock_instance.ehlo.assert_called()
        mock_instance.starttls.assert_called_once()
        mock_instance.login.assert_called_once_with("notifications@example.com", "test-secure-password")
        mock_instance.send_message.assert_called_once_with(msg)


@pytest.mark.asyncio
async def test_send_password_reset_email(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    with patch.object(service, "send_email") as mock_send:
        await service.send_password_reset_email(
            to_email="user@example.com",
            user_name="John Doe",
            username="johndoe",
            reset_url="http://localhost:5173/reset-password?token=dummy-token",
        )

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "user@example.com"
        assert "Reset your HRMS password" in args[1]
        assert "http://localhost:5173/reset-password?token=dummy-token" in args[2]  # HTML body
        assert "user@example.com" in args[2]  # Email in HTML body
        assert "http://localhost:5173/reset-password?token=dummy-token" in args[3]  # Text body
        assert "user@example.com" in args[3]  # Email in text body


@pytest.mark.asyncio
async def test_send_user_invitation_email(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    with patch.object(service, "send_email") as mock_send:
        await service.send_user_invitation_email(
            to_email="member@example.com",
            user_name="Jane Doe",
            username="janedoe",
            role_name="HR_MANAGER",
            invite_url="http://localhost:5173/set-password?token=invite-token",
        )

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "member@example.com"
        assert "You're invited to HRMS" in args[1]
        assert "http://localhost:5173/set-password?token=invite-token" in args[2]  # HTML body
        assert "member@example.com" in args[2]  # Email in HTML body
        assert "HR MANAGER" in args[2]  # Formatted role in HTML body
        assert "48 hours" in args[2]  # Expiration notice in HTML body


@pytest.mark.asyncio
async def test_send_verification_email(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    with patch.object(service, "send_email") as mock_send:
        await service.send_verification_email(
            to_email="new_email@example.com",
            user_name="Jane Doe",
            verify_url="http://localhost:5173/verify-email?token=verify-token",
        )

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "new_email@example.com"
        assert "Verify your email address for HRMS" in args[1]
        assert "http://localhost:5173/verify-email?token=verify-token" in args[2]  # HTML body
        assert "new_email@example.com" in args[2]  # Email in HTML body
        assert "http://localhost:5173/verify-email?token=verify-token" in args[3]  # Text body
        assert "new_email@example.com" in args[3]  # Email in text body


@pytest.mark.asyncio
async def test_send_email_changed_alert(mock_settings):
    service = EmailService()
    service.settings = mock_settings

    with patch.object(service, "send_email") as mock_send:
        await service.send_email_changed_alert(
            old_email="old@example.com",
            new_email="new@example.com",
        )

        mock_send.assert_called_once()
        args, kwargs = mock_send.call_args
        assert args[0] == "old@example.com"
        assert "Security Alert: Email Address Changed" in args[1]
        assert "old@example.com" in args[2]  # Old email in HTML body
        assert "new@example.com" in args[2]  # New email in HTML body
        assert "old@example.com" in args[3]  # Old email in text body
        assert "new@example.com" in args[3]  # New email in text body
