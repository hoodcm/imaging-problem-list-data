"""add warning payload support to jobs

Revision ID: e8f4a1b2c3d4
Revises: c7a3d2e4f5b8
Create Date: 2026-02-15 00:00:00.000000

"""

from collections.abc import Sequence

import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f4a1b2c3d4"
down_revision: str | Sequence[str] | None = "c7a3d2e4f5b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add warning payload column and expand jobs status constraint."""
    with op.batch_alter_table("jobs", schema=None, recreate="always") as batch_op:
        batch_op.add_column(
            sqlmodel.Column("warning_payload_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.drop_constraint("check_job_status", type_="check")
        batch_op.create_check_constraint(
            "check_job_status",
            "status IN ('pending', 'running', 'completed', 'completed_with_warnings', 'failed')",
        )


def downgrade() -> None:
    """Remove warning payload column and restore previous jobs status constraint."""
    with op.batch_alter_table("jobs", schema=None, recreate="always") as batch_op:
        batch_op.drop_constraint("check_job_status", type_="check")
        batch_op.create_check_constraint(
            "check_job_status",
            "status IN ('pending', 'running', 'completed', 'failed')",
        )
        batch_op.drop_column("warning_payload_json")
