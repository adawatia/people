from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi_users import exceptions as fu_exceptions
from fastapi_users.password import PasswordHelper
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import UserManager, get_user_manager
from db.models import AuthSession, Employee
from sqlalchemy import update
from core.database import get_async_session
from core.invitation import find_user_by_invitation_token
from db.models import now_ist
from schemas import SetPasswordRequest, ValidateInvitationResponse

router = APIRouter(prefix="/auth/invitation", tags=["auth"])


@router.get(
    "/validate",
    response_model=ValidateInvitationResponse,
    summary="Validate an invitation token",
)
async def validate_invitation_token(
    token: str,
    session: AsyncSession = Depends(get_async_session),
):
    user, error = await find_user_by_invitation_token(session, token)
    if not user:
        return ValidateInvitationResponse(
            valid=False,
            detail=error or "Invitation link is invalid or expired.",
        )

    employee = await session.scalar(select(Employee).where(Employee.user_id == user.id))
    role_name = employee.role if employee else "EMPLOYEE"

    return ValidateInvitationResponse(
        valid=True,
        email=user.email,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role_name=role_name,
    )


@router.post(
    "/set-password",
    summary="Complete invitation and set user password",
)
async def set_password_from_invitation(
    payload: SetPasswordRequest,
    request: Request,
    user_manager: UserManager = Depends(get_user_manager),
    session: AsyncSession = Depends(get_async_session),
):
    user, error = await find_user_by_invitation_token(session, payload.token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or "Invalid or expired invitation token.",
        )

    # Strictly validate the new password against password complexity rules
    try:
        await user_manager.validate_password(payload.password, user)
    except fu_exceptions.InvalidPasswordException as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "REGISTER_INVALID_PASSWORD",
                "reason": e.reason,
            },
        )

    # Hash the password and activate user
    helper = PasswordHelper()
    user.hashed_password = helper.hash(payload.password)
    user.invitation_used_at = now_ist()
    user.invitation_token_hash = None
    user.is_active = True
    user.is_verified = True
    user.must_change_password = False
    await session.execute(update(AuthSession).where(
        AuthSession.user_id == user.id,
        AuthSession.revoked_at.is_(None),
    ).values(revoked_at=now_ist()))

    await session.commit()
    return {"message": "Password successfully created. You can now log in."}
