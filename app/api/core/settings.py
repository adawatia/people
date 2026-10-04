import json
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.secret_box import DEVELOPMENT_KEY as DEVELOPMENT_MFA_KEY


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
    expose_api_docs: bool = Field(default=False, alias="EXPOSE_API_DOCS")

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
    erp_api_clients: str = Field(default="", alias="ERP_API_CLIENTS")
    erp_signature_max_age_seconds: int = Field(default=300, ge=30, le=900, alias="ERP_SIGNATURE_MAX_AGE_SECONDS")
    bootstrap_seed_data: bool = Field(default=False, alias="BOOTSTRAP_SEED_DATA")

    # ── Authentication: token and session policy ───────────────────────────────
    # All TTLs are seconds unless the name says otherwise.  The defaults are the
    # production-safe values; a deployment may shorten them but never needs to
    # lengthen them to be secure.
    access_token_ttl_seconds: int = Field(default=900, ge=60, le=3600, alias="ACCESS_TOKEN_TTL_SECONDS")
    # Legacy bearer token minted by the password flow (Swagger / non-browser
    # clients).  It is a *single-purpose* exchange credential now: long enough
    # for an immediate POST /auth/session, far too short to be a usable session.
    login_exchange_token_ttl_seconds: int = Field(default=300, ge=30, le=900, alias="LOGIN_EXCHANGE_TOKEN_TTL_SECONDS")
    refresh_token_ttl_seconds: int = Field(default=30 * 24 * 3600, ge=3600, alias="REFRESH_TOKEN_TTL_SECONDS")

    # Idle/absolute limits bound how long a stolen refresh token stays useful,
    # independently of its own TTL.  Business sessions get a working day.
    session_idle_timeout_seconds: int = Field(default=60 * 60, ge=300, alias="SESSION_IDLE_TIMEOUT_SECONDS")
    session_absolute_timeout_seconds: int = Field(default=12 * 3600, ge=1800, alias="SESSION_ABSOLUTE_TIMEOUT_SECONDS")
    # Privileged (Super Admin) sessions are deliberately much tighter.
    privileged_access_token_ttl_seconds: int = Field(
        default=300, ge=60, le=900, alias="PRIVILEGED_ACCESS_TOKEN_TTL_SECONDS"
    )
    privileged_idle_timeout_seconds: int = Field(default=15 * 60, ge=120, alias="PRIVILEGED_IDLE_TIMEOUT_SECONDS")
    privileged_absolute_timeout_seconds: int = Field(
        default=2 * 3600, ge=600, alias="PRIVILEGED_ABSOLUTE_TIMEOUT_SECONDS"
    )

    # ── Authentication: brute-force protection ────────────────────────────────
    # failed attempts before a key starts collecting a progressive delay / block.
    auth_throttle_max_failures: int = Field(default=5, ge=1, alias="AUTH_THROTTLE_MAX_FAILURES")
    auth_throttle_window_seconds: int = Field(default=900, ge=60, alias="AUTH_THROTTLE_WINDOW_SECONDS")
    auth_throttle_block_seconds: int = Field(default=60, ge=1, alias="AUTH_THROTTLE_BLOCK_SECONDS")
    auth_throttle_max_block_seconds: int = Field(default=3600, ge=60, alias="AUTH_THROTTLE_MAX_BLOCK_SECONDS")
    auth_refresh_max_failures: int = Field(default=20, ge=1, alias="AUTH_REFRESH_MAX_FAILURES")
    # ``memory`` (single process only) or ``redis`` (required for >1 worker).
    auth_throttle_backend: str = Field(default="memory", alias="AUTH_THROTTLE_BACKEND")
    redis_url: str = Field(default="", alias="REDIS_URL")
    # Only enable behind a proxy you control: any reachable client could forge
    # X-Forwarded-For and escape per-IP throttling.
    trust_proxy_headers: bool = Field(default=False, alias="TRUST_PROXY_HEADERS")

    # ── Authentication: MFA ───────────────────────────────────────────────────
    # Enforcement is opt-in per deployment so enabling it is a deliberate,
    # communicated rollout (existing operators must enrol first).  A deployed
    # Super Admin should have MFA_REQUIRED_FOR_SUPER_ADMIN=true; the startup
    # warning calls that out until it is.
    mfa_enabled: bool = Field(default=True, alias="MFA_ENABLED")
    mfa_required_for_super_admin: bool = Field(default=False, alias="MFA_REQUIRED_FOR_SUPER_ADMIN")
    mfa_issuer: str = Field(default="People HRMS", alias="MFA_ISSUER")
    mfa_challenge_ttl_seconds: int = Field(default=300, ge=60, le=900, alias="MFA_CHALLENGE_TTL_SECONDS")
    password_recovery_ttl_seconds: int = Field(default=600, ge=60, le=1800, alias="PASSWORD_RECOVERY_TTL_SECONDS")
    mfa_pending_ttl_seconds: int = Field(default=900, ge=60, le=86400, alias="MFA_PENDING_TTL_SECONDS")
    sensitive_action_mfa_max_age_seconds: int = Field(
        default=600, ge=60, le=3600, alias="SENSITIVE_ACTION_MFA_MAX_AGE_SECONDS"
    )
    # AES-256 key protecting TOTP seeds at rest (base64).  This key must live
    # outside the database - a dump that also contains the key protects nothing -
    # and it is separate from the JWT key on purpose: rotating a signing key, or
    # configuring MFA on a deployment that signs with a different secret, must
    # not destroy every enrolled authenticator.  Empty means "not set" and falls
    # back to the development key, so a copied .env.example behaves exactly like
    # an absent variable instead of silently failing every MFA write.
    mfa_encryption_key: str = Field(default="", alias="MFA_ENCRYPTION_KEY")

    # ── Password policy ───────────────────────────────────────────────────────
    password_min_length: int = Field(default=8, ge=8, alias="PASSWORD_MIN_LENGTH")
    # Argon2 has no bcrypt-style truncation, but an unbounded password is a
    # cheap way to burn server CPU, so keep a generous ceiling.
    password_max_length: int = Field(default=256, ge=64, alias="PASSWORD_MAX_LENGTH")
    # ``off`` (default), ``local`` (embedded common-password list), or
    # ``remote`` (configured HTTP checker).  A breached-password check must never
    # make sign-in depend on a third party being reachable, so ``remote`` fails
    # open and logs.
    password_breach_check: str = Field(default="local", alias="PASSWORD_BREACH_CHECK")
    password_breach_check_url: str = Field(default="", alias="PASSWORD_BREACH_CHECK_URL")

    @property
    def is_development(self) -> bool:
        return self.environment.lower() in {"development", "dev", "test", "local"}

    def validate_runtime_secrets(self) -> None:
        """Reject development defaults when the API is started outside development.

        Keeping convenient local defaults is useful for contributors, but silently
        accepting them in a deployed HR system is not.  This guard is called at
        application startup rather than at import time so Alembic and local tools
        can still load configuration deliberately.

        The development shortcut is keyed on an explicit allow-list of
        environment names rather than "anything that is not production", so a
        typo such as ``ENVIRONMENT=Production`` cannot silently disable every
        hardening check below.
        """
        if self.is_development:
            return

        try:
            erp_clients = json.loads(self.erp_api_clients)
            erp_clients_valid = (
                bool(erp_clients)
                and isinstance(erp_clients, dict)
                and all(
                    isinstance(client_id, str)
                    and client_id.strip()
                    and isinstance(config, dict)
                    and len(str(config.get("secret", ""))) >= 32
                    and isinstance(config.get("scopes"), list)
                    and bool(config["scopes"])
                    for client_id, config in erp_clients.items()
                )
            )
        except json.JSONDecodeError, TypeError:
            erp_clients_valid = False

        insecure = {
            "JWT_SECRET": self.jwt_secret == "hrms-jwt-secret-key-32chars-min-2026-auth",
            "DATABASE_URL": self.database_url == "postgresql+psycopg://dev:SuperAdmin@localhost:5432/hrms",
            "SUPER_ADMIN_PASSWORD": self.super_admin_password == "SuperAdmin@123",
            "ERP_API_CLIENTS": not erp_clients_valid,
            "AUTH_THROTTLE_BACKEND": self.auth_throttle_backend != "redis",
            "REDIS_URL": self.auth_throttle_backend == "redis" and not self.redis_url,
            "MFA_ENCRYPTION_KEY": self.mfa_secret_key() == DEVELOPMENT_MFA_KEY,
            "MFA_REQUIRED_FOR_SUPER_ADMIN": not self.mfa_enabled or not self.mfa_required_for_super_admin,
        }
        missing = [name for name, is_insecure in insecure.items() if is_insecure]
        if missing:
            raise RuntimeError(f"Production configuration requires secure values for: {', '.join(missing)}")

    def security_warnings(self) -> list[str]:
        """Non-fatal hardening reminders, logged once at startup."""
        warnings: list[str] = []
        if self.auth_throttle_backend != "redis":
            warnings.append(
                "AUTH_THROTTLE_BACKEND=memory keeps login throttling per worker; "
                "configure Redis before running more than one API worker"
            )
        if not self.mfa_enabled:
            warnings.append("MFA_ENABLED=false: privileged sign-in is password-only")
        elif not self.mfa_required_for_super_admin:
            warnings.append("MFA_REQUIRED_FOR_SUPER_ADMIN=false: Super Admin MFA is optional")
        if self.password_breach_check == "remote" and not self.password_breach_check_url:
            warnings.append(
                "PASSWORD_BREACH_CHECK=remote without PASSWORD_BREACH_CHECK_URL falls back to the local list"
            )
        if self.mfa_secret_key() == DEVELOPMENT_MFA_KEY:
            warnings.append(
                "MFA_ENCRYPTION_KEY is the development default: enrolled authenticator secrets "
                "are encrypted with a key that is public in the repository"
            )
        if not self.trust_proxy_headers:
            warnings.append(
                "TRUST_PROXY_HEADERS=false: every request behind a proxy/BFF shares one "
                "client IP, so per-IP throttling treats the whole deployment as one source"
            )
        return warnings

    def mfa_secret_key(self) -> str:
        """The key used to encrypt TOTP seeds at rest.

        A single accessor so exactly one place decides *which* key protects
        seeds: an unset (or empty) variable resolves to the development key here
        rather than at every call site, and production validation compares the
        resolved value.
        """
        return (self.mfa_encryption_key or "").strip() or DEVELOPMENT_MFA_KEY

    def resolved_database_url(self) -> str:
        configured_database_url = self.database_url.strip()
        if configured_database_url:
            return configured_database_url

        password = self.postgres_password
        auth = self.postgres_user if not password else f"{self.postgres_user}:{password}"
        return f"postgresql+asyncpg://{auth}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    def resolved_database_url_sync(self) -> str:
        url = self.resolved_database_url()
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
        return url


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
