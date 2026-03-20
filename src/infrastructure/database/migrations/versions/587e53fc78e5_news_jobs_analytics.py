"""News, jobs, and analytics tables.

Squashed migration: news_items, jobs, analytics_ai tables
and related column additions to users and exchange_rates.

Revision ID: 587e53fc78e5
Revises: fc447514f941
Create Date: 2026-03-16 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "587e53fc78e5"
down_revision: Union[str, None] = "fc447514f941"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── news_items ──
    op.create_table(
        "news_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.String(5000), nullable=False),
        sa.Column(
            "sources",
            postgresql.ARRAY(sa.String),
            nullable=True,
        ),
        sa.Column(
            "article_urls",
            postgresql.ARRAY(sa.String(2048)),
            nullable=True,
        ),
        sa.Column(
            "bookmarked",
            sa.Boolean,
            nullable=False,
            server_default="f",
        ),
        sa.Column("reaction", sa.String(10), nullable=True),
        sa.Column(
            "detailed_description",
            sa.String(5000),
            nullable=True,
        ),
        sa.Column(
            "extended_description",
            sa.String(5000),
            nullable=True,
        ),
        sa.Column(
            "human_feedback",
            sa.String(5000),
            nullable=True,
        ),
        sa.Column(
            "needs_ai_analysis",
            sa.Boolean,
            nullable=False,
            server_default="f",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_news_items_created_at",
        "news_items",
        ["created_at"],
    )
    op.create_index(
        "ix_news_items_reaction",
        "news_items",
        ["reaction"],
    )
    op.create_index(
        "ix_news_items_needs_ai_analysis",
        "news_items",
        ["needs_ai_analysis"],
    )

    # ── jobs ──
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column(
            "_metadata",
            postgresql.JSONB,
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "interval_minutes",
            sa.Integer,
            nullable=True,
        ),
        sa.Column(
            "is_active",
            sa.Boolean,
            nullable=False,
            server_default="t",
        ),
        sa.Column(
            "last_run_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "next_run_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "last_status",
            sa.String(20),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.String(1000),
            nullable=True,
        ),
        sa.Column(
            "run_count",
            sa.Integer,
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )

    # ── analytics_ai ──
    op.create_table(
        "analytics_ai",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "pipeline_name",
            sa.String(255),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(12), nullable=False),
        sa.Column(
            "agent_stats",
            postgresql.JSONB,
            nullable=False,
        ),
        sa.Column("total_calls", sa.Integer, nullable=False),
        sa.Column("total_errors", sa.Integer, nullable=False),
        sa.Column("wall_time_s", sa.Float, nullable=False),
        sa.Column("estimated_cost", sa.Float, nullable=False),
        sa.Column(
            "user_id",
            sa.Integer,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_analytics_ai_created_at",
        "analytics_ai",
        ["created_at"],
    )

    # ── users: news preference columns ──
    op.add_column(
        "users",
        sa.Column(
            "news_filter_prompt",
            sa.String(5000),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "news_preference_profile",
            sa.String(10000),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "gc_retention_days",
            sa.Integer,
            nullable=False,
            server_default="3",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "analyze_preferences",
            sa.Boolean,
            nullable=False,
            server_default="t",
        ),
    )

    # ── exchange_rates: source column ──
    op.add_column(
        "exchange_rates",
        sa.Column(
            "source",
            sa.String(20),
            nullable=True,
            server_default="nbu",
        ),
    )


def downgrade() -> None:
    op.drop_column("exchange_rates", "source")
    op.drop_column("users", "analyze_preferences")
    op.drop_column("users", "gc_retention_days")
    op.drop_column("users", "news_preference_profile")
    op.drop_column("users", "news_filter_prompt")
    op.drop_table("analytics_ai")
    op.drop_table("jobs")
    op.drop_table("news_items")
