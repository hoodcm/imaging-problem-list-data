"""add section_structure_json column to reports

Revision ID: b5e2a9f1c3d7
Revises: 17d9bf28412d
Create Date: 2026-02-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "b5e2a9f1c3d7"
down_revision: Union[str, Sequence[str], None] = "17d9bf28412d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add section_structure_json column to reports table."""
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("section_structure_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove section_structure_json column from reports table."""
    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_column("section_structure_json")
