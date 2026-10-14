"""Create the normalized catalog, import receipts, and Finisher-owned flags."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_create_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_jobs",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("row_counts", postgresql.JSONB(), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_import_jobs_idempotency_key"),
    )
    op.create_table(
        "finishers",
        sa.Column("finisher_id", sa.Text(), primary_key=True),
        sa.Column("finisher_name", sa.Text(), nullable=False),
        sa.Column("hq_country", sa.Text(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "suppliers",
        sa.Column("supplier_id", sa.Text(), primary_key=True),
        sa.Column("supplier_name", sa.Text(), nullable=False),
        sa.Column("hq_country", sa.Text(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "factories",
        sa.Column("factory_id", sa.Text(), primary_key=True),
        sa.Column("supplier_id", sa.Text(), sa.ForeignKey("suppliers.supplier_id"), nullable=False),
        sa.Column("factory_name", sa.Text(), nullable=False),
        sa.Column("address_line", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "parts",
        sa.Column("part_id", sa.Text(), primary_key=True),
        sa.Column("part_name", sa.Text(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "part_sources",
        sa.Column("part_id", sa.Text(), sa.ForeignKey("parts.part_id"), primary_key=True),
        sa.Column("factory_id", sa.Text(), sa.ForeignKey("factories.factory_id"), primary_key=True),
        sa.Column("unit_cost_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
        sa.CheckConstraint("unit_cost_usd >= 0", name="ck_part_sources_unit_cost_nonnegative"),
    )
    op.create_table(
        "toys",
        sa.Column("toy_id", sa.Text(), primary_key=True),
        sa.Column("toy_name", sa.Text(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
    )
    op.create_table(
        "finisher_toys",
        sa.Column(
            "finisher_id", sa.Text(), sa.ForeignKey("finishers.finisher_id"), primary_key=True
        ),
        sa.Column("toy_id", sa.Text(), sa.ForeignKey("toys.toy_id"), primary_key=True),
        sa.Column("retail_price_usd", sa.Numeric(12, 2), nullable=False),
        sa.Column("units_per_year", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
        sa.CheckConstraint("retail_price_usd >= 0", name="ck_finisher_toys_price_nonnegative"),
        sa.CheckConstraint("units_per_year >= 0", name="ck_finisher_toys_volume_nonnegative"),
    )
    op.create_table(
        "bom_items",
        sa.Column("toy_id", sa.Text(), sa.ForeignKey("toys.toy_id"), primary_key=True),
        sa.Column("part_id", sa.Text(), sa.ForeignKey("parts.part_id"), primary_key=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "created_by_import_job_id",
            sa.BigInteger(),
            sa.ForeignKey("import_jobs.id"),
            nullable=False,
        ),
        sa.CheckConstraint("quantity > 0", name="ck_bom_items_quantity_positive"),
    )
    op.create_table(
        "finisher_supplier_flags",
        sa.Column(
            "finisher_id", sa.Text(), sa.ForeignKey("finishers.finisher_id"), primary_key=True
        ),
        sa.Column(
            "supplier_id", sa.Text(), sa.ForeignKey("suppliers.supplier_id"), primary_key=True
        ),
        sa.Column("flagged_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("idx_factories_supplier", "factories", ["supplier_id"])
    op.create_index("idx_part_sources_factory", "part_sources", ["factory_id"])
    op.create_index("idx_bom_items_part", "bom_items", ["part_id"])
    op.create_index("idx_finisher_toys_toy", "finisher_toys", ["toy_id"])


def downgrade() -> None:
    op.drop_index("idx_finisher_toys_toy", table_name="finisher_toys")
    op.drop_index("idx_bom_items_part", table_name="bom_items")
    op.drop_index("idx_part_sources_factory", table_name="part_sources")
    op.drop_index("idx_factories_supplier", table_name="factories")
    op.drop_table("finisher_supplier_flags")
    op.drop_table("bom_items")
    op.drop_table("finisher_toys")
    op.drop_table("toys")
    op.drop_table("part_sources")
    op.drop_table("parts")
    op.drop_table("factories")
    op.drop_table("suppliers")
    op.drop_table("finishers")
    op.drop_table("import_jobs")
