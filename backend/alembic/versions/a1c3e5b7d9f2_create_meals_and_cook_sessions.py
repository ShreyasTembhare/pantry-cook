"""create meals, meal lines, and cook sessions

Revision ID: a1c3e5b7d9f2
Revises: 9fe7e08524d7
Create Date: 2026-09-28 21:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c3e5b7d9f2"
down_revision: str | Sequence[str] | None = "9fe7e08524d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meals",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("sentence", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("servings", sa.Integer(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("cook_session_id", sa.String(), nullable=True),
        sa.Column("cooked_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.CheckConstraint("servings >= 1 AND servings <= 24", name="ck_meals_servings"),
        sa.CheckConstraint(
            "status IN ('proposed', 'cooked', 'undone')",
            name="ck_meals_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cook_session_id"),
    )
    op.create_index("ix_meals_created_at", "meals", ["created_at"], unique=False)

    op.create_table(
        "meal_lines",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("meal_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("item_name_snapshot", sa.String(), nullable=False),
        sa.Column("quantity_base", sa.Float(), nullable=True),
        sa.Column("dimension", sa.String(), nullable=True),
        sa.Column("display_unit", sa.String(), nullable=True),
        sa.Column("missing_name", sa.String(), nullable=True),
        sa.Column("missing_note", sa.String(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint("kind IN ('use', 'missing')", name="ck_meal_lines_kind"),
        sa.CheckConstraint(
            "quantity_base IS NULL OR quantity_base >= 0",
            name="ck_meal_lines_quantity_non_negative",
        ),
        sa.ForeignKeyConstraint(["item_id"], ["items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meal_lines_meal_id", "meal_lines", ["meal_id"], unique=False)

    op.create_table(
        "cook_sessions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("sentence", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.JSON(), nullable=True),
        sa.Column("meal_id", sa.String(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('running', 'awaiting_user', 'committed', 'abandoned', 'failed')",
            name="ck_cook_sessions_status",
        ),
        sa.ForeignKeyConstraint(["meal_id"], ["meals.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_cook_sessions_status_expires_at",
        "cook_sessions",
        ["status", "expires_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_cook_sessions_status_expires_at", table_name="cook_sessions")
    op.drop_table("cook_sessions")
    op.drop_index("ix_meal_lines_meal_id", table_name="meal_lines")
    op.drop_table("meal_lines")
    op.drop_index("ix_meals_created_at", table_name="meals")
    op.drop_table("meals")
