"""add body_region and contrast columns to extractions

Revision ID: d4f2a8b1c6e3
Revises: 9c5b7d1e2a4f
Create Date: 2026-02-26 00:00:00.000000

"""

from collections.abc import Sequence

import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4f2a8b1c6e3"
down_revision: str | Sequence[str] | None = "9c5b7d1e2a4f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add body_region and contrast columns to extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("body_region", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sqlmodel.Column("contrast", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )


def downgrade() -> None:
    """Remove body_region and contrast columns from extractions table."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_column("contrast")
        batch_op.drop_column("body_region")
