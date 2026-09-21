from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://dev:SuperAdmin@localhost:5432/hrms",
        alias="DATABASE_URL",
    )
    jwt_secret: str = Field(default="hrms-jwt-secret-key-32chars-min-2026-auth", alias="JWT_SECRET")
    environment: str = Field(default="development", alias="ENVIRONMENT")

    # Logging (12-factor: stdout by default; file appender is opt-in, e.g. prod)
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    log_format: str = Field(default="console", alias="LOG_FORMAT")
    log_to_file: bool = Field(default=False, alias="LOG_TO_FILE")
    log_dir: str = Field(default="logs", alias="LOG_DIR")
    log_file_name: str = Field(default="api.log", alias="LOG_FILE_NAME")
    log_file_max_bytes: int = Field(default=10 * 1024 * 1024, alias="LOG_FILE_MAX_BYTES")
    log_file_backup_count: int = Field(default=5, alias="LOG_FILE_BACKUP_COUNT")
    postgres_host: str = Field(default="localhost", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_user: str = Field(default="postgres", alias="POSTGRES_USER")
    postgres_password: str = Field(default="", alias="POSTGRES_PASSWORD")
    postgres_db: str = Field(default="hrms", alias="POSTGRES_DB")
    super_admin_email: str = Field(default="admin@hrms.com", alias="SUPER_ADMIN_EMAIL")
    super_admin_username: str = Field(default="superadmin", alias="SUPER_ADMIN_USERNAME")
    super_admin_password: str = Field(default="SuperAdmin@123", alias="SUPER_ADMIN_PASSWORD")
    super_admin_first_name: str = Field(default="Super", alias="SUPER_ADMIN_FIRST_NAME")
    super_admin_last_name: str = Field(default="Admin", alias="SUPER_ADMIN_LAST_NAME")

    # Mail SMTP Configuration
    mail_server: str = Field(default="smtppro.zoho.com", alias="MAIL_SERVER")
    mail_port: int = Field(default=587, alias="MAIL_PORT")
    mail_username: str = Field(default="", alias="MAIL_USERNAME")
    mail_password: str = Field(default="", alias="MAIL_PASSWORD")
    mail_from: str = Field(default="", alias="MAIL_FROM")
    mail_starttls: bool = Field(default=True, alias="MAIL_STARTTLS")
    mail_ssl_tls: bool = Field(default=False, alias="MAIL_SSL_TLS")
    use_credentials: bool = Field(default=True, alias="USE_CREDENTIALS")
    validate_certs: bool = Field(default=True, alias="VALIDATE_CERTS")
    
    frontend_url: str = Field(default="http://192.168.103.20:3000", alias="FRONTEND_URL")

    # API Keys for M2M Integration
    api_key: str = Field(default="hrms_api_key_dev_only", alias="API_KEY")
    erp_api_key: str = Field(default="", alias="ERP_API_KEY")
    bootstrap_seed_data: bool = Field(default=False, alias="BOOTSTRAP_SEED_DATA")

    def validate_runtime_secrets(self) -> None:
        """Reject development defaults when the API is started outside development.

        Keeping convenient local defaults is useful for contributors, but silently
        accepting them in a deployed HR system is not.  This guard is called at
        application startup rather than at import time so Alembic and local tools
        can still load configuration deliberately.
        """
        if self.environment.lower() in {"development", "dev", "test"}:
            return

        insecure = {
            "JWT_SECRET": self.jwt_secret == "hrms-jwt-secret-key-32chars-min-2026-auth",
            "DATABASE_URL": self.database_url == "postgresql+psycopg://dev:SuperAdmin@localhost:5432/hrms",
            "SUPER_ADMIN_PASSWORD": self.super_admin_password == "SuperAdmin@123",
            "ERP_API_KEY": not self.erp_api_key,
        }
        missing = [name for name, is_insecure in insecure.items() if is_insecure]
        if missing:
            raise RuntimeError(f"Production configuration requires secure values for: {', '.join(missing)}")

    def resolved_database_url(self) -> str:
        configured_database_url = self.database_url.strip()
        if configured_database_url:
            return configured_database_url

        password = self.postgres_password
        auth = self.postgres_user if not password else f"{self.postgres_user}:{password}"
        return (
            f"postgresql+asyncpg://{auth}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def resolved_database_url_sync(self) -> str:
        url = self.resolved_database_url()
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return url



@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
