from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from core.database import async_session_maker
from core.database import auth_engine as engine
from core.settings import get_settings
from db.models import Base, Organization, User


async def create_db_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_seed_data(
    *,
    username: str | None = None,
    password: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    organization_name: str | None = None,
    organization_code: str | None = None,
    force_update_credentials: bool = False,
) -> User:
    settings = get_settings()
    async with async_session_maker() as session:
        organization = await session.scalar(select(Organization).order_by(Organization.id.asc()))
        if organization is None:
            session.add(
                Organization(
                    name=organization_name or settings.organization_name,
                    short_name=organization_code or settings.organization_code,
                )
            )
            await session.flush()
        target_email = email or settings.super_admin_email
        target_username = username or settings.super_admin_username
        target_password = password or settings.super_admin_password
        target_first_name = first_name or settings.super_admin_first_name
        target_last_name = last_name or settings.super_admin_last_name

        user = await session.scalar(
            select(User).where((User.email == target_email) | (User.username == target_username))
        )
        if user is None:
            user = await session.scalar(select(User).where(User.is_superuser.is_(True)).order_by(User.id.asc()))
        if user is None:
            user = User(
                email=target_email,
                username=target_username,
                first_name=target_first_name,
                last_name=target_last_name,
                hashed_password=PasswordHelper().hash(target_password),
                is_active=True,
                is_verified=True,
                is_superuser=True,
            )
            session.add(user)
        else:
            if force_update_credentials:
                user.email = target_email
                user.username = target_username
                user.first_name = target_first_name
                user.last_name = target_last_name
                user.hashed_password = PasswordHelper().hash(target_password)
            user.is_active = True
            user.is_verified = True
            user.is_superuser = True

        await session.commit()
        await session.refresh(user)
        return user
