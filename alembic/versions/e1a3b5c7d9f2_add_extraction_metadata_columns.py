"""add extraction metadata columns (exam info, diagnostics, coding counts, trace_id)

Revision ID: e1a3b5c7d9f2
Revises: d4f2a8b1c6e3
Create Date: 2026-02-27 00:00:00.000000

"""

from collections.abc import Sequence

import sqlmodel
from sqlalchemy import text

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1a3b5c7d9f2"
down_revision: str | Sequence[str] | None = "d4f2a8b1c6e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add metadata columns to extractions: laterality, finding_count, coding counts, diagnostics, trace_id."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.add_column(
            sqlmodel.Column("laterality", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(sqlmodel.Column("finding_count", sqlmodel.Integer(), nullable=True))
        batch_op.add_column(
            sqlmodel.Column("coding_coded_count", sqlmodel.Integer(), nullable=True)
        )
        batch_op.add_column(
            sqlmodel.Column("coding_unresolved_count", sqlmodel.Integer(), nullable=True)
        )
        batch_op.add_column(
            sqlmodel.Column("diagnostics_json", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )
        batch_op.add_column(
            sqlmodel.Column("trace_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True)
        )

    # Backfill study_description and finding_count from extraction_json for existing rows.
    conn = op.get_bind()
    conn.execute(
        text(
            "UPDATE extractions SET study_description = "
            "json_extract(extraction_json, '$.exam_info.study_description') "
            "WHERE study_description IS NULL"
        )
    )
    conn.execute(
        text(
            "UPDATE extractions SET finding_count = "
            "json_array_length(json_extract(extraction_json, '$.findings')) "
            "WHERE finding_count IS NULL"
        )
    )


def downgrade() -> None:
    """Remove metadata columns from extractions."""
    with op.batch_alter_table("extractions", schema=None) as batch_op:
        batch_op.drop_column("trace_id")
        batch_op.drop_column("diagnostics_json")
        batch_op.drop_column("coding_unresolved_count")
        batch_op.drop_column("coding_coded_count")
        batch_op.drop_column("finding_count")
        batch_op.drop_column("laterality")
