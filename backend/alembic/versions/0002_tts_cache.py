"""tts_cache: synthesized audio with LRU eviction

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tts_cache",
        sa.Column("hash", sa.String(64), primary_key=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("voice_id", sa.String(120), nullable=False),
        sa.Column("model", sa.String(80), nullable=False),
        sa.Column("mime", sa.String(40), nullable=False),
        sa.Column("audio", sa.LargeBinary(), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tts_cache_last_used", "tts_cache", ["last_used_at"])


def downgrade() -> None:
    op.drop_index("ix_tts_cache_last_used", table_name="tts_cache")
    op.drop_table("tts_cache")
