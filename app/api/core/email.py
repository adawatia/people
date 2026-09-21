"""Email delivery service used by authentication and workflow notifications.

The implementation remains in the former module during this transition; this
stable core import is the supported application boundary.
"""

from legacy.email import EmailService, email_service, get_email_service

__all__ = ["EmailService", "email_service", "get_email_service"]
