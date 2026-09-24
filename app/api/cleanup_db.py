"""Remove all application rows while preserving the PostgreSQL schema.

The command is a read-only preview unless every destructive guard is supplied::

    uv run python cleanup_db.py
    uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA"
    uv run python cleanup_db.py --execute --confirm "DELETE ALL HRMS DATA" --reseed-bootstrap

``alembic_version`` is always preserved so the remaining schema stays aligned
with the migration history. Stop the API before executing this command: in a
development environment, API startup may recreate bootstrap organization and
Super Admin rows.
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

CONFIRMATION = "DELETE ALL HRMS DATA"
PRESERVED_TABLES = frozenset({"alembic_version"})
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
        help="Recreate the bootstrap organization and Super Admin from environment settings after cleanup.",
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


async def reseed_bootstrap() -> None:
    """Recreate the minimum records required to sign in after a reset."""
    from core.database import auth_engine
    from db.seed import ensure_seed_data

    try:
        await ensure_seed_data()
    finally:
        await auth_engine.dispose()


def print_preview(url: URL, schema: str, tables: Sequence[str]) -> None:
    print(f"Database: {url.render_as_string(hide_password=True)}")
    print(f"Schema:   {schema}")
    print(f"Preserved: {', '.join(sorted(PRESERVED_TABLES))}")
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
        print_preview(url, args.schema, tables)

        if not args.execute:
            print(f'\nPreview only. To delete these rows, rerun with --execute --confirm "{CONFIRMATION}".')
            return 0

        if not tables:
            return 0

        statement = f"TRUNCATE TABLE {qualified_tables(engine, args.schema, tables)} RESTART IDENTITY CASCADE"
        with engine.begin() as connection:
            connection.exec_driver_sql(statement)
        print(f"\nEmptied {len(tables)} application tables and reset their owned identity sequences.")
        if args.reseed_bootstrap:
            asyncio.run(reseed_bootstrap())
            settings = get_settings()
            print(
                "Recreated the bootstrap organization and Super Admin "
                f"({settings.super_admin_username!r}, {settings.super_admin_email!r})."
            )
        else:
            print(
                "The Super Admin was deleted with the other rows. Development API startup recreates it, "
                "or rerun cleanup with --reseed-bootstrap."
            )
        return 0
    except (CleanupRefused, OSError, RuntimeError, SQLAlchemyError) as exc:
        print(f"Database cleanup failed: {exc}", file=sys.stderr)
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
