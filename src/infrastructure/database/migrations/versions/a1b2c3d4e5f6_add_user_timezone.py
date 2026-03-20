"""add user timezone

Revision ID: a1b2c3d4e5f6
Revises: d8a213ae1732
Create Date: 2026-03-17 14:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "d8a213ae1732"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(50),
            server_default="UTC",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone")
