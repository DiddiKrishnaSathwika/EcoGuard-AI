"""Add tenant ownership and OIDC memberships.

Revision ID: 0002_tenant_auth
Revises: 0001_initial_schema
Create Date: 2026-11-26
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_tenant_auth"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("issuer", sa.Text(), nullable=False),
        sa.Column("subject", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "issuer", "subject"),
    )
    op.add_column(
        "business_profiles",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_business_profiles_tenant_id",
        "business_profiles",
        "tenants",
        ["tenant_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_business_profiles_tenant_id",
        "business_profiles",
        ["tenant_id"],
    )


def downgrade():
    raise RuntimeError(
        "Destructive downgrades are disabled; create a forward migration instead."
    )
