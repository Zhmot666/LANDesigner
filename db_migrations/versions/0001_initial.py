"""Initial schema (ProjectMeta + Site)."""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_meta",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("origin", sa.String(length=64), nullable=False, server_default="local"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "site",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False, server_default=""),
        sa.Column("notes", sa.String(length=2000), nullable=False, server_default=""),
        sa.ForeignKeyConstraint(["project_id"], ["project_meta.id"], ondelete="CASCADE"),
    )


def downgrade() -> None:
    op.drop_table("site")
    op.drop_table("project_meta")

