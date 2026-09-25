"""add user status

Revision ID: 131009c326a2
Revises: 7af2864342a3
Create Date: 2026-09-23 00:23:52.673979

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '131009c326a2'
down_revision: Union[str, Sequence[str], None] = '7af2864342a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "users",
        sa.Column("status", sa.Text(), nullable=True)
    )
    
    op.execute("""
        UPDATE users
        SET status = 'active'
        WHERE status IS NULL;
    """)
    
    op.alter_column(
        "users",
        "status",
        nullable=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "status")
