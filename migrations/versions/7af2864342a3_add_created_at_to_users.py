"""add created_at to users

Revision ID: 7af2864342a3
Revises: b134ae81b456
Create Date: 2026-09-22 22:54:36.466598

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7af2864342a3'
down_revision: Union[str, Sequence[str], None] = 'b134ae81b456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        ALTER TABLE users
        ADD COLUMN created_at TIMESTAMP;
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        ALTER TABLE users
        DROP COLUMN created_at;
    """)
