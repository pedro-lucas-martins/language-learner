"""feedback on messages, flashcards table

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("feedback", sa.Text(), nullable=True))
    op.create_table(
        "flashcards",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("front", sa.Text(), nullable=False),
        sa.Column("back", sa.Text(), nullable=False),
        sa.Column("word", sa.String(120), nullable=True),
        sa.Column("lang", sa.String(5), nullable=False),
        sa.Column(
            "source_message_id",
            sa.Uuid(),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("ease", sa.Float(), nullable=False),
        sa.Column("interval_days", sa.Integer(), nullable=False),
        sa.Column("repetitions", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('grammar', 'pronunciation')", name="ck_flashcards_kind"),
        sa.UniqueConstraint("user_id", "kind", "front", name="uq_flashcards_user_kind_front"),
    )
    op.create_index("ix_flashcards_user_due", "flashcards", ["user_id", "due_at"])


def downgrade() -> None:
    op.drop_index("ix_flashcards_user_due", table_name="flashcards")
    op.drop_table("flashcards")
    op.drop_column("messages", "feedback")
