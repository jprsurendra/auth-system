"""Add composite indexes for query performance

Revision ID: 0002
Revises:     0001

Why these indexes matter:

idx_audit_logs_user_created
  Query: WHERE user_id = ? ORDER BY created_at DESC
  Without: full table scan — gets slower as logs grow
  With:    instant lookup — critical for multi-module
           projects where every module writes audit logs

idx_sessions_user_valid  (PARTIAL INDEX)
  Query: WHERE user_id = ? AND is_valid = true
  Without: scans all sessions including old ones
  With:    only indexes active sessions — stays small
           forever regardless of how many old sessions
           accumulate over time

Both use CONCURRENTLY — no table lock during creation.
Safe to run on a live production database.
"""
from __future__ import annotations

from alembic import op


revision      = "0002"
down_revision = "0001"
branch_labels = None
depends_on    = None


def upgrade() -> None:

    # Composite index — user_id + created_at DESC
    op.create_index(
        index_name="idx_audit_logs_user_created",
        table_name="audit_logs",
        columns=["user_id", "created_at"],
        postgresql_ops={"created_at": "DESC"},
        postgresql_concurrently=True,
    )

    # Partial index — only active sessions
    op.create_index(
        index_name="idx_sessions_user_valid",
        table_name="user_sessions",
        columns=["user_id"],
        postgresql_where="is_valid = true",
        postgresql_concurrently=True,
    )


def downgrade() -> None:
    op.drop_index(
        "idx_audit_logs_user_created",
        table_name="audit_logs",
    )
    op.drop_index(
        "idx_sessions_user_valid",
        table_name="user_sessions",
    )
