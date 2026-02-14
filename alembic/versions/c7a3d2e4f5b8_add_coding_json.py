"""add coding_json column to extractions

Revision ID: c7a3d2e4f5b8
Revises: b5e2a9f1c3d7
Create Date: 2026-02-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "c7a3d2e4f5b8"
down_revision: Union[str, Sequence[str], None] = "b5e2a9f1c3d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add coding_json column to extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("coding_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove coding_json column from extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_column("coding_json")
