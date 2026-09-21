import os

from fastapi_users.password import PasswordHelper
from sqlalchemy import select

from core.database import async_session_maker
from core.database import auth_engine as engine
from db.models import Base, Organization, User


async def create_db_and_tables() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def ensure_seed_data() -> None:
    async with async_session_maker() as session:
        organization = await session.scalar(select(Organization).order_by(Organization.id.asc()))
        if organization is None:
            session.add(Organization(
                name=os.getenv("ORGANIZATION_NAME", "My Organization"),
                short_name=os.getenv("ORGANIZATION_CODE", "ORG"),
            ))
            await session.flush()
        email = os.getenv("SUPER_ADMIN_EMAIL", "admin@hrms.com")
        username = os.getenv("SUPER_ADMIN_USERNAME", "superadmin")
        password = os.getenv("SUPER_ADMIN_PASSWORD", "SuperAdmin@123")
        first_name = os.getenv("SUPER_ADMIN_FIRST_NAME", "Super")
        last_name = os.getenv("SUPER_ADMIN_LAST_NAME", "Admin")

        user = await session.scalar(select(User).where((User.email == email) | (User.username == username)))
        if user is None:
            user = await session.scalar(select(User).where(User.is_superuser.is_(True)).order_by(User.id.asc()))
        if user is None:
            user = User(
                email=email,
                username=username,
                first_name=first_name,
                last_name=last_name,
                hashed_password=PasswordHelper().hash(password),
                is_active=True,
                is_verified=True,
                is_superuser=True,
            )
            session.add(user)
        else:
            # Never overwrite credentials here: the Super Admin can change
            # username/password from the application settings page.
            user.is_active = True
            user.is_verified = True
            user.is_superuser = True

        await session.commit()
