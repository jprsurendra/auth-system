"""Initial schema — users, user_sessions, audit_logs

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00
"""
from __future__ import annotations

import alembic.op as op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:

    # ── users ──────────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column(
            "id", sa.String(36),
            primary_key=True, nullable=False
        ),
        sa.Column(
            "username", sa.String(30),
            nullable=False
        ),
        sa.Column(
            "email", sa.String(254),
            nullable=False
        ),
        sa.Column(
            "phone", sa.String(20),
            nullable=False
        ),
        sa.Column(
            "full_name", sa.String(150),
            nullable=False
        ),
        sa.Column(
            "hashed_password", sa.String(128),
            nullable=True
        ),
        sa.Column(
            "google_sub", sa.String(128),
            nullable=True
        ),
        sa.Column(
            "email_verified", sa.Boolean(),
            nullable=False, server_default="false"
        ),
        sa.Column(
            "phone_verified", sa.Boolean(),
            nullable=False, server_default="false"
        ),
        sa.Column(
            "is_active", sa.Boolean(),
            nullable=False, server_default="true"
        ),
        sa.Column(
            "is_superuser", sa.Boolean(),
            nullable=False, server_default="false"
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.UniqueConstraint("email",    name="uq_users_email"),
        sa.UniqueConstraint("phone",    name="uq_users_phone"),
        sa.UniqueConstraint("username", name="uq_users_username"),
        sa.UniqueConstraint("google_sub", name="uq_users_google_sub"),
    )
    op.create_index("ix_users_email",    "users", ["email"])
    op.create_index("ix_users_phone",    "users", ["phone"])
    op.create_index("ix_users_username", "users", ["username"])

    # ── user_sessions ──────────────────────────────────────────────────────────
    op.create_table(
        "user_sessions",
        sa.Column(
            "id", sa.String(36),
            primary_key=True, nullable=False
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey(
                "users.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column(
            "token_hash", sa.String(64),
            nullable=False, unique=True
        ),
        sa.Column(
            "is_valid", sa.Boolean(),
            nullable=False, server_default="true"
        ),
        sa.Column(
            "user_agent", sa.String(512),
            nullable=True
        ),
        sa.Column(
            "ip_address", sa.String(45),
            nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "expires_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_sessions_user_id",
        "user_sessions", ["user_id"]
    )
    op.create_index(
        "ix_sessions_token_hash",
        "user_sessions", ["token_hash"]
    )

    # ── audit_logs ─────────────────────────────────────────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column(
            "id", sa.Integer(),
            primary_key=True,
            autoincrement=True,
            nullable=False,
        ),
        sa.Column(
            "user_id", sa.String(36),
            sa.ForeignKey(
                "users.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "event", sa.String(64),
            nullable=False
        ),
        sa.Column(
            "ip_address", sa.String(45),
            nullable=True
        ),
        sa.Column(
            "user_agent", sa.String(512),
            nullable=True
        ),
        sa.Column(
            "detail", sa.Text(),
            nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_audit_user_id",
        "audit_logs", ["user_id"]
    )
    op.create_index(
        "ix_audit_event",
        "audit_logs", ["event"]
    )
    op.create_index(
        "ix_audit_created_at",
        "audit_logs", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("user_sessions")
    op.drop_table("users")
