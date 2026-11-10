"""initial: users, chat_sessions, messages, usage_events

Revision ID: 0001
Revises:
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("native_lang", sa.String(5), nullable=False),
        sa.Column("target_lang", sa.String(5), nullable=False),
        sa.Column("level", sa.String(2), nullable=False),
        sa.Column("user_facts", sa.Text(), nullable=False),
        sa.Column("voice_id", sa.String(120), nullable=True),
        sa.Column("recast_pronunciation", sa.Boolean(), nullable=False),
        sa.Column("access_token_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("native_lang IN ('pt-BR', 'pl-PL')", name="ck_users_native_lang"),
        sa.CheckConstraint("target_lang IN ('pt-BR', 'pl-PL')", name="ck_users_target_lang"),
        sa.CheckConstraint("native_lang <> target_lang", name="ck_users_langs_differ"),
        sa.CheckConstraint("level IN ('A1', 'A2', 'B1', 'B2', 'C1')", name="ck_users_level"),
    )
    op.create_index("ix_users_access_token_hash", "users", ["access_token_hash"], unique=True)

    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("running_summary", sa.Text(), nullable=False),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(4), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user', 'ai')", name="ck_messages_role"),
    )
    op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])

    op.create_table(
        "usage_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_usage_user_kind_created", "usage_events", ["user_id", "kind", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_usage_user_kind_created", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_table("messages")
    op.drop_table("chat_sessions")
    op.drop_index("ix_users_access_token_hash", table_name="users")
    op.drop_table("users")
