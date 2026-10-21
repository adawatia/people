"""Remove all application rows while preserving the PostgreSQL schema.

The command is a read-only preview unless every destructive guard is supplied::

    uv run python cleanup_db.py
    uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA"
    uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap
    uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap --admin-username myadmin --admin-password "StrongPass123!"

``alembic_version`` and Super Admin login accounts are preserved by default so
the cleaned installation remains recoverable. Stop the API before executing.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import URL, Connection, Engine, make_url
from sqlalchemy.exc import SQLAlchemyError

from core.settings import get_settings
from db.models import User

CONFIRMATION = "DELETE ALL HRMS DATA"
PRESERVED_TABLES = frozenset({"alembic_version", "users"})
LOCAL_HOSTS = frozenset({None, "", "localhost", "127.0.0.1", "::1"})


class CleanupRefused(RuntimeError):
    """Raised when a destructive execution guard is not satisfied."""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or remove every row from HRMS PostgreSQL tables while preserving the schema.",
    )
    parser.add_argument("--execute", action="store_true", help="Execute TRUNCATE. Omit this flag for a preview.")
    parser.add_argument(
        "--confirm",
        default="",
        metavar=f'"{CONFIRMATION}"',
        help="Required exact confirmation text when --execute is used.",
    )
    parser.add_argument("--schema", default="public", help="PostgreSQL schema to clean (default: public).")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="Permit execution when DATABASE_URL does not point to localhost.",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Permit execution when ENVIRONMENT is not development, dev, test, or local.",
    )
    parser.add_argument(
        "--reseed-bootstrap",
        action="store_true",
        help="Recreate the bootstrap organization and Super Admin after cleanup.",
    )
    parser.add_argument(
        "--delete-super-admin",
        action="store_true",
        help="Also delete Super Admin accounts. Use only when --reseed-bootstrap will recreate one.",
    )
    parser.add_argument(
        "--admin-username",
        help="Custom Super Admin username to use during --reseed-bootstrap (defaults to SUPER_ADMIN_USERNAME in .env).",
    )
    parser.add_argument(
        "--admin-password",
        help="Custom Super Admin password to use during --reseed-bootstrap (defaults to SUPER_ADMIN_PASSWORD in .env).",
    )
    parser.add_argument(
        "--admin-email",
        help="Custom Super Admin email to use during --reseed-bootstrap (defaults to SUPER_ADMIN_EMAIL in .env).",
    )
    parser.add_argument(
        "--admin-first-name",
        help="Custom Super Admin first name to use during --reseed-bootstrap.",
    )
    parser.add_argument(
        "--admin-last-name",
        help="Custom Super Admin last name to use during --reseed-bootstrap.",
    )
    return parser.parse_args()


def database_url() -> URL:
    url = make_url(get_settings().resolved_database_url_sync())
    if url.get_backend_name() != "postgresql":
        raise CleanupRefused(f"Only PostgreSQL is supported; configured backend is {url.get_backend_name()!r}.")
    return url


def application_tables(connection: Connection, schema: str) -> list[str]:
    return sorted(
        table_name
        for table_name in inspect(connection).get_table_names(schema=schema)
        if table_name not in PRESERVED_TABLES
    )


def qualified_tables(engine: Engine, schema: str, tables: Sequence[str]) -> str:
    quote = engine.dialect.identifier_preparer.quote
    quote_schema = engine.dialect.identifier_preparer.quote_schema
    return ", ".join(f"{quote_schema(schema)}.{quote(table)}" for table in tables)


def validate_execution(args: argparse.Namespace, url: URL) -> None:
    if args.confirm != CONFIRMATION:
        raise CleanupRefused(f'Execution requires --confirm "{CONFIRMATION}".')
    if url.host not in LOCAL_HOSTS and not args.allow_remote:
        raise CleanupRefused(
            f"Refusing to clean remote host {url.host!r}; add --allow-remote only after checking DATABASE_URL."
        )
    settings = get_settings()
    if not settings.is_development and not args.allow_production:
        raise CleanupRefused(
            f"Refusing to clean ENVIRONMENT={settings.environment!r}; add --allow-production only for an intentional reset."
        )
    if args.delete_super_admin and not args.reseed_bootstrap:
        raise CleanupRefused("--delete-super-admin requires --reseed-bootstrap so the database stays accessible.")


async def reseed_bootstrap(
    *,
    username: str | None = None,
    password: str | None = None,
    email: str | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    force_update_credentials: bool = False,
) -> User:
    """Recreate the minimum records required to sign in after a reset."""
    from core.database import auth_engine
    from db.seed import ensure_seed_data

    try:
        return await ensure_seed_data(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            last_name=last_name,
            force_update_credentials=force_update_credentials,
        )
    finally:
        await auth_engine.dispose()


def print_preview(url: URL, schema: str, tables: Sequence[str]) -> None:
    print(f"Database: {url.render_as_string(hide_password=True)}")
    print(f"Schema:   {schema}")
    print("Preserved: alembic_version and Super Admin login accounts")
    print("Workforce login accounts in users will be deleted.")
    if not tables:
        print("No application tables were found.")
        return
    print(f"Tables to empty ({len(tables)}):")
    for table in tables:
        print(f"  - {table}")


def main() -> int:
    args = parse_args()
    engine: Engine | None = None
    try:
        url = database_url()
        if args.reseed_bootstrap and not args.execute:
            raise CleanupRefused("--reseed-bootstrap requires --execute.")
        if args.execute:
            validate_execution(args, url)
        engine = create_engine(url, pool_pre_ping=True)
        with engine.connect() as connection:
            tables = application_tables(connection, args.schema)
        if args.delete_super_admin:
            tables = sorted([*tables, "users"])
        print_preview(url, args.schema, tables)

        if not args.execute:
            print(f'\nPreview only. To delete these rows, rerun with --execute --confirm "{CONFIRMATION}".')
            return 0

        if not tables:
            return 0

        statement = f"TRUNCATE TABLE {qualified_tables(engine, args.schema, tables)} RESTART IDENTITY CASCADE"
        with engine.begin() as connection:
            connection.exec_driver_sql(statement)
            if not args.delete_super_admin:
                users_table = qualified_tables(engine, args.schema, ["users"])
                connection.exec_driver_sql(f"DELETE FROM {users_table} WHERE is_superuser IS NOT TRUE")
        print(f"\nEmptied {len(tables)} application tables and reset their owned identity sequences.")
        if args.reseed_bootstrap:
            force_update = bool(
                args.delete_super_admin
                or args.admin_username
                or args.admin_password
                or args.admin_email
                or args.admin_first_name
                or args.admin_last_name
            )
            admin_user = asyncio.run(
                reseed_bootstrap(
                    username=args.admin_username,
                    password=args.admin_password,
                    email=args.admin_email,
                    first_name=args.admin_first_name,
                    last_name=args.admin_last_name,
                    force_update_credentials=force_update,
                )
            )
            print(
                "Configured the bootstrap organization and Super Admin "
                f"(username: {admin_user.username!r}, email: {admin_user.email!r})."
            )
        else:
            print("Super Admin login accounts were preserved; workforce accounts were removed.")
        return 0
    except (CleanupRefused, OSError, RuntimeError, SQLAlchemyError) as exc:
        print(f"Database cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
