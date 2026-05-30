from __future__ import annotations
import secrets
from functools import lru_cache
from typing import Literal
from pydantic import AnyHttpUrl, EmailStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # App
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "AuthService"
    APP_VERSION: str = "1.0.0"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False

    # Security
    SECRET_KEY: str = secrets.token_urlsafe(64)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OTP_EXPIRE_SECONDS: int = 600
    OTP_LENGTH: int = 6
    OTP_HMAC_KEY: str = secrets.token_urlsafe(32)

    # CORS
    ALLOWED_ORIGINS: list[AnyHttpUrl] = ["http://localhost:3000"]
    ALLOWED_HOSTS: list[str] = ["localhost", "127.0.0.1"]

    # Cookie
    COOKIE_SECURE: bool = True
    COOKIE_SAMESITE: Literal["strict", "lax", "none"] = "strict"
    COOKIE_DOMAIN: str | None = None

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://user:pass@localhost:5432/authdb"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_PRE_PING: bool = True

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_MAX_CONNECTIONS: int = 50

    # Rate limiting
    RATE_LIMIT_OTP_MAX: int = 5
    RATE_LIMIT_OTP_WINDOW_SECONDS: int = 900
    RATE_LIMIT_LOGIN_MAX: int = 10
    RATE_LIMIT_LOGIN_WINDOW_SECONDS: int = 600
    RATE_LIMIT_REGISTER_MAX: int = 3
    RATE_LIMIT_REGISTER_WINDOW_SECONDS: int = 3600

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # SendGrid
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: EmailStr = "noreply@example.com"
    EMAIL_FROM_NAME: str = "AuthService"

    # Google OAuth
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/google/callback"

    # Sentry
    SENTRY_DSN: str = ""

    # Support error notifications
    SUPPORT_EMAIL: EmailStr = "support@yourdomain.com"
    SUPPORT_EMAIL_NAME: str = "Support Team"
    ERROR_NOTIFICATIONS_ENABLED: bool = True
    IPAPI_URL: str = "https://ipapi.co"




    @field_validator("DATABASE_URL")
    @classmethod
    def validate_db_url(cls, v: str) -> str:
        if not v.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the asyncpg driver")
        return v

    @model_validator(mode="after")
    def production_checks(self) -> "Settings":
        if self.APP_ENV == "production":
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be True in production")
        return self

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
