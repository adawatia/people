import secrets
import string
from datetime import datetime, timedelta

from fastapi import HTTPException, status
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from sqlalchemy.ext.asyncio import AsyncSession

from core.audit import add_audit_event
from core.auth import UserManager
from core.settings import get_settings
from db.models import User, now_ist
from repositories.user_admin_repo import UserAdminRepository
from schemas.users import PaginatedTechnicalAccountsResponse, TechnicalAccountRead
from services.auth_service import AuditAction, AuthService


class UserAdminService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = UserAdminRepository(session)
        self.manager = UserManager(SQLAlchemyUserDatabase(session, User))

    @staticmethod
    def require_super_admin(actor: User) -> None:
        if not actor.is_superuser:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Technical administrator access required")

    def verify_step_up(self, actor: User, password: str, *, session_mfa_verified_at: datetime | None = None) -> None:
        verified, _ = self.manager.password_helper.verify_and_update(password, actor.hashed_password)
        if not verified:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
        settings = get_settings()
        if getattr(actor, "mfa_enabled", False) or settings.mfa_required_for_super_admin:
            verified_at = session_mfa_verified_at
            if verified_at is None or verified_at < now_ist() - timedelta(
                seconds=settings.sensitive_action_mfa_max_age_seconds
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "RECENT_MFA_REQUIRED",
                        "message": "Verify your authenticator again before performing this action.",
                    },
                )

    async def list_accounts(self, actor: User, **filters) -> PaginatedTechnicalAccountsResponse:
        self.require_super_admin(actor)
        page, employees = await self.repo.account_page(**filters)
        items = []
        for user in page["items"]:
            employee = employees.get(user.id)
            items.append(
                TechnicalAccountRead(
                    id=user.id,
                    username=user.username,
                    email=str(user.email),
                    first_name=user.first_name,
                    last_name=user.last_name,
                    mobile_number=user.mobile_number,
                    is_active=user.is_active,
                    is_verified=user.is_verified,
                    must_change_password=user.must_change_password,
                    mfa_enabled=user.mfa_enabled,
                    created_at=user.created_at,
                    employee_id=employee.id if employee else None,
                    employee_code=employee.employee_code if employee else None,
                    employee_role=employee.role if employee else None,
                )
            )
        return PaginatedTechnicalAccountsResponse(**{**page, "items": items})

    async def _target(
        self,
        actor: User,
        user_id: int,
        current_password: str,
        *,
        session_mfa_verified_at: datetime | None = None,
    ) -> User:
        self.require_super_admin(actor)
        self.verify_step_up(actor, current_password, session_mfa_verified_at=session_mfa_verified_at)
        target = await self.repo.get_workforce_user(user_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workforce account not found")
        return target

    async def _temporary_password(self, user: User) -> str:
        alphabet = string.ascii_letters + string.digits + "!@#$%&*?"
        chooser = secrets.SystemRandom()
        while True:
            characters = [
                secrets.choice(string.ascii_uppercase),
                secrets.choice(string.ascii_lowercase),
                secrets.choice(string.digits),
                secrets.choice("!@#$%&*?"),
                *(secrets.choice(alphabet) for _ in range(16)),
            ]
            chooser.shuffle(characters)
            password = "".join(characters)
            try:
                await self.manager.validate_password(password, user)
            except InvalidPasswordException:
                continue
            return password

    async def reset_password(
        self,
        actor: User,
        user_id: int,
        current_password: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
        session_mfa_verified_at: datetime | None = None,
    ) -> tuple[str, int]:
        target = await self._target(actor, user_id, current_password, session_mfa_verified_at=session_mfa_verified_at)
        temporary_password = await self._temporary_password(target)
        target.hashed_password = self.manager.password_helper.hash(temporary_password)
        target.must_change_password = True
        target.password_recovery_token_hash = None
        target.password_recovery_expires_at = None
        revoked = await AuthService(self.session).revoke_all(
            target,
            actor=actor,
            reason="password_reset:super_admin",
            action=AuditAction.PASSWORD_RESET,
            ip_address=ip_address,
            request_id=request_id,
        )
        return temporary_password, revoked

    async def revoke_sessions(
        self,
        actor: User,
        user_id: int,
        current_password: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
        session_mfa_verified_at: datetime | None = None,
    ) -> int:
        target = await self._target(actor, user_id, current_password, session_mfa_verified_at=session_mfa_verified_at)
        return await AuthService(self.session).revoke_all(
            target,
            actor=actor,
            reason="super_admin_support",
            ip_address=ip_address,
            request_id=request_id,
        )

    async def set_active(
        self,
        actor: User,
        user_id: int,
        current_password: str,
        is_active: bool,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
        session_mfa_verified_at: datetime | None = None,
    ) -> int:
        target = await self._target(actor, user_id, current_password, session_mfa_verified_at=session_mfa_verified_at)
        target.is_active = is_active
        if not is_active:
            return await AuthService(self.session).revoke_all(
                target,
                actor=actor,
                reason="account_suspended:super_admin",
                action=AuditAction.ACCOUNT_STATUS_CHANGED,
                ip_address=ip_address,
                request_id=request_id,
            )
        add_audit_event(
            self.session,
            actor=actor,
            action=AuditAction.ACCOUNT_STATUS_CHANGED,
            entity_type="user",
            entity_id=str(target.id),
            filters={"is_active": True, "revoked_sessions": 0},
            ip_address=ip_address,
            request_id=request_id,
        )
        await self.session.commit()
        return 0

    async def reset_mfa(
        self,
        actor: User,
        user_id: int,
        current_password: str,
        *,
        ip_address: str | None = None,
        request_id: str | None = None,
        session_mfa_verified_at: datetime | None = None,
    ) -> int:
        target = await self._target(actor, user_id, current_password, session_mfa_verified_at=session_mfa_verified_at)
        target.mfa_enabled = False
        target.mfa_secret = None
        target.mfa_pending_secret = None
        target.mfa_pending_expires_at = None
        target.mfa_enrolled_at = None
        target.mfa_last_used_step = None
        target.mfa_recovery_code_hashes = None
        target.last_mfa_verified_at = None
        return await AuthService(self.session).revoke_all(
            target,
            actor=actor,
            reason="mfa_reset:super_admin",
            action=AuditAction.MFA_ADMIN_RESET,
            ip_address=ip_address,
            request_id=request_id,
        )
