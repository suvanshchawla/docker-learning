"""add email to users

Revision ID: b134ae81b456
Revises: 
Create Date: 2026-09-22 22:45:15.122096

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b134ae81b456'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        CREATE TABLE users (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        email TEXT
        );
    """)
    pass


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        DROP TABLE users;
               
    """)
    pass
