"""leave approval fields

Revision ID: fa65d1d38e37
Revises: 31e72c4c5dfe
Create Date: 2026-11-13 11:30:31.038235

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'fa65d1d38e37'
down_revision: Union[str, Sequence[str], None] = '31e72c4c5dfe'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("manager_id", sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_users_manager", "users", "users", ["manager_id"], ["id"])
    op.create_index("ix_users_manager_id", "users", ["manager_id"])
    op.add_column("leave_requests", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.add_column("leave_requests", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True))
 
 
def downgrade() -> None:
    op.drop_column("leave_requests", "decided_at")
    op.drop_column("leave_requests", "decision_reason")
    op.drop_index("ix_users_manager_id", table_name="users")
    op.drop_constraint("fk_users_manager", "users", type_="foreignkey")
    op.drop_column("users", "manager_id")
    op.drop_column("users", "full_name")
 
