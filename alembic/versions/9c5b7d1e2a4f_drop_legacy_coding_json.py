"""drop legacy coding_json column from extractions

Revision ID: 9c5b7d1e2a4f
Revises: e8f4a1b2c3d4
Create Date: 2026-02-17 00:00:00.000000

"""

from collections.abc import Sequence

import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9c5b7d1e2a4f"
down_revision: str | Sequence[str] | None = "e8f4a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop detached coding payload column after inline-coding cutover."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_column("coding_json")


def downgrade() -> None:
    """Restore detached coding payload column."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("coding_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )

