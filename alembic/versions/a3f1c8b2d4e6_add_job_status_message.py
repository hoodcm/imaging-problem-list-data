"""add status_message column to jobs

Revision ID: a3f1c8b2d4e6
Revises: 7537480089ba
Create Date: 2026-02-11 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "a3f1c8b2d4e6"
down_revision: Union[str, Sequence[str], None] = "7537480089ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add status_message column to jobs table."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("status_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove status_message column from jobs table."""
    with op.batch_alter_table("jobs", schema=None) as batch_op:
        batch_op.drop_column("status_message")
