from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


# ── User ───────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email",    name="uq_users_email"),
        UniqueConstraint("phone",    name="uq_users_phone"),
        UniqueConstraint("username", name="uq_users_username"),
        Index("ix_users_email",    "email"),
        Index("ix_users_phone",    "phone"),
        Index("ix_users_username", "username"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    username: Mapped[str] = mapped_column(
        String(30), nullable=False
    )
    email: Mapped[str] = mapped_column(
        String(254), nullable=False
    )
    # E.164 format, e.g. +919876543210
    phone: Mapped[str] = mapped_column(
        String(20), nullable=False
    )
    full_name: Mapped[str] = mapped_column(
        String(150), nullable=False
    )

    # Nullable — Google-OAuth-only users have no password
    hashed_password: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )

    # Google OAuth
    google_sub: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )

    # Verification flags
    email_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    phone_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Account state
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    is_superuser: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    # Timestamps — all UTC
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    sessions: Mapped[list[UserSession]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog",
        back_populates="user",
    )

    @property
    def is_fully_verified(self) -> bool:
        return self.email_verified and self.phone_verified

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"


# ── UserSession ────────────────────────────────────────────────────────────────

class UserSession(Base):
    """
    One row per issued refresh token.
    We store only the SHA-256 hash of the raw token —
    a full DB dump never exposes a valid session token.
    Rotation sets is_valid=False on the old row
    and inserts a new row for the new token.
    """
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_sessions_user_id",   "user_id"),
        Index("ix_sessions_token_hash", "token_hash"),
    )

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=_new_uuid
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # SHA-256 hex digest of the raw refresh token
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    is_valid: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )

    # Context — useful for "active sessions" management UI
    user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    # IPv6-safe length
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped[User] = relationship(
        "User", back_populates="sessions"
    )


# ── AuditLog ───────────────────────────────────────────────────────────────────

class AuditLog(Base):
    """
    Immutable security event log.
    Never updated or deleted — append-only.
    Captures: register, login, logout, verify, failed attempts,
              token reuse detection, password resets.
    """
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_id",   "user_id"),
        Index("ix_audit_event",     "event"),
        Index("ix_audit_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    # Nullable — pre-registration events have no user_id yet
    user_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    event: Mapped[str] = mapped_column(
        String(64), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )
    # JSON blob for extra context (e.g. which field failed validation)
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    user: Mapped[User | None] = relationship(
        "User", back_populates="audit_logs"
    )
