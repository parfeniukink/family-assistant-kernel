"""add exchange_rates table

Revision ID: 2a3b4c5d6e7f
Revises: 1637d76700ba
Create Date: 2026-02-03 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, None] = "1637d76700ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "exchange_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("currency_code", sa.String(length=3), nullable=False),
        sa.Column("rate", sa.Float(), nullable=False),
        sa.Column("exchange_date", sa.DATE(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_exchange_rates")),
        sa.UniqueConstraint(
            "currency_code",
            "exchange_date",
            name="uq_exchange_rates_code_date",
        ),
    )


def downgrade() -> None:
    op.drop_table("exchange_rates")
