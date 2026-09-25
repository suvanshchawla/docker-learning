"""add role to users

Revision ID: 6c1daceb59a6
Revises: 131009c326a2
Create Date: 2026-09-25 17:09:14.446909

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c1daceb59a6'
down_revision: Union[str, Sequence[str], None] = '131009c326a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('role', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'role')
