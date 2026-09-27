"""Request/response contracts for authentication and session management.

Kept in the schemas layer so both the login and session routers (and the MFA
router) describe the same shapes, and so clients have one contract to code
against.  Nothing here contains secrets: the refresh token is the only raw
credential that ever appears in a response, and only to the trusted BFF.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RefreshSessionRequest(BaseModel):
    refresh_token: str = Field(..., min_length=16, description="Opaque refresh token issued by login or refresh")
    model_config = {"json_schema_extra": {"example": {"refresh_token": "replace-with-refresh-token"}}}


class SessionIssuedResponse(BaseModel):
    """Credential bundle issued to a trusted client."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="Access-token lifetime in seconds")
    session_id: int
    refresh_expires_at: datetime
    absolute_expires_at: datetime = Field(..., description="Hard end of this session chain, however often refreshed")


class SessionSummaryResponse(BaseModel):
    """Non-secret description of one signed-in session."""

    id: int
    created_at: datetime
    last_used_at: datetime | None = None
    expires_at: datetime
    absolute_expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    is_current: bool = False


class MessageResponse(BaseModel):
    message: str
    revoked_sessions: int | None = None


class LoginResponse(BaseModel):
    """Login outcome: either a session, or a second-factor challenge."""

    access_token: str | None = None
    refresh_token: str | None = None
    token_type: str = "bearer"
    expires_in: int | None = None
    session_id: int | None = None
    refresh_expires_at: datetime | None = None
    absolute_expires_at: datetime | None = None
    must_change_password: bool = False
    # Set instead of the tokens above when a second factor (including first-time
    # MFA enrolment) is required for this account.
    mfa_required: bool = False
    mfa_enrollment_required: bool = False
    mfa_token: str | None = None
    mfa_expires_in: int | None = None


class MfaChallengeRequest(BaseModel):
    """Second-factor request carrying the short-lived challenge token."""

    mfa_token: str = Field(..., min_length=16, description="Challenge token returned by login")
    code: str = Field(..., min_length=4, max_length=32, description="TOTP code or a recovery code")


class MfaEnrollRequest(BaseModel):
    mfa_token: str = Field(..., min_length=16)


class MfaPasswordRequest(BaseModel):
    """Authenticated MFA management operations re-verify the password (step-up)."""

    current_password: str = Field(min_length=1)


class MfaConfirmRequest(MfaPasswordRequest):
    """Confirm a newly issued authenticator secret from an authenticated session.

    Used when an account opts into MFA from account settings, rather than during
    a login challenge: the password is re-verified *and* the code must match the
    pending secret before the factor is enabled.
    """

    code: str = Field(..., min_length=4, max_length=32, description="TOTP code from the new authenticator")


class MfaEnrollmentResponse(BaseModel):
    """One-time view of a new authenticator secret."""

    secret: str
    otpauth_uri: str = Field(..., description="otpauth:// URI to render as a QR code")
    recovery_codes: list[str] = Field(
        ...,
        description=(
            "Single-use codes, shown only once. Empty when replacing an existing "
            "authenticator: the current codes stay valid until explicitly "
            "regenerated, so an abandoned replacement cannot invalidate them."
        ),
    )
    replacing_existing: bool = Field(
        default=False,
        description="True when an active authenticator keeps working until this one is confirmed",
    )


class MfaRecoveryCodesResponse(BaseModel):
    """A freshly issued set of single-use recovery codes (shown only once)."""

    recovery_codes: list[str]
    recovery_codes_remaining: int


class MfaStatusResponse(BaseModel):
    """Enrolment state. Never includes the secret, its URI or the codes."""

    enabled: bool
    enrolled_at: datetime | None = None
    last_verified_at: datetime | None = None
    recovery_codes_remaining: int = 0
    replacement_pending: bool = Field(
        default=False,
        description="A replacement authenticator has been issued but not yet confirmed",
    )


class PasswordRecoveryStartRequest(BaseModel):
    identity: str = Field(..., min_length=1, max_length=120)


class PasswordRecoveryStartResponse(BaseModel):
    message: str
    recovery_token: str
    expires_in: int


class PasswordRecoveryVerifyRequest(BaseModel):
    recovery_token: str = Field(..., min_length=16)
    code: str = Field(..., min_length=4, max_length=32)


class PasswordRecoveryResetRequest(BaseModel):
    reset_token: str = Field(..., min_length=16)
    new_password: str = Field(..., min_length=1, description="Must satisfy the configured password policy")
