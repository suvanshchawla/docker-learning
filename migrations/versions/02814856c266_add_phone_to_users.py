"""add phone to users

Revision ID: 02814856c266
Revises: 6c1daceb59a6
Create Date: 2026-09-25 17:18:03.761058

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '02814856c266'
down_revision: Union[str, Sequence[str], None] = '6c1daceb59a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('phone', sa.String(length=15), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'phone')
