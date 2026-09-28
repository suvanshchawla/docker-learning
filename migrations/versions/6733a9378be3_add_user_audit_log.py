"""add user audit log

Revision ID: 6733a9378be3
Revises: 02814856c266
Create Date: 2026-09-28 17:01:19.748038

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6733a9378be3'
down_revision: Union[str, Sequence[str], None] = '02814856c266'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE user_audit_log (
            id SERIAL PRIMARY KEY,
            user_id INTEGER NOT NULL,
            action TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE user_audit_log;
    """)
