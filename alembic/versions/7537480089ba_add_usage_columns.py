"""add usage columns to extractions

Revision ID: 7537480089ba
Revises: 17f8ebc6c608
Create Date: 2026-02-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "7537480089ba"
down_revision: Union[str, Sequence[str], None] = "17f8ebc6c608"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add token usage and duration columns to extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.add_column(sa.Column("input_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("output_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cache_read_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cache_write_tokens", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("model_requests", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("duration_ms", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("usage_details_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove token usage and duration columns from extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_column("usage_details_json")
        batch_op.drop_column("duration_ms")
        batch_op.drop_column("model_requests")
        batch_op.drop_column("cache_write_tokens")
        batch_op.drop_column("cache_read_tokens")
        batch_op.drop_column("output_tokens")
        batch_op.drop_column("input_tokens")
