"""drop filter_meta from analytics_ai

Revision ID: d8a213ae1732
Revises: 587e53fc78e5
Create Date: 2026-03-17 11:46:10.094394

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d8a213ae1732"
down_revision: Union[str, None] = "587e53fc78e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("analytics_ai", "filter_meta")


def downgrade() -> None:
    op.add_column(
        "analytics_ai",
        sa.Column(
            "filter_meta",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
