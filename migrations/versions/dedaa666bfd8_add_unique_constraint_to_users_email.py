"""add unique constraint to users email

Revision ID: dedaa666bfd8
Revises: 6733a9378be3
Create Date: 2026-10-03 19:24:04.228701

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'dedaa666bfd8'
down_revision: Union[str, Sequence[str], None] = '6733a9378be3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Refuse to guess which duplicate to keep: emails that differ only by case
    # must be resolved by a person before this migration can run.
    duplicates = op.get_bind().execute(
        sa.text(
            """
            SELECT lower(email), count(*)
            FROM users
            GROUP BY lower(email)
            HAVING count(*) > 1
            """
        )
    ).fetchall()
    if duplicates:
        listing = ", ".join(f"{email} ({count} rows)" for email, count in duplicates)
        raise RuntimeError(
            f"Cannot make users.email unique: duplicate emails found: {listing}. "
            "Fix or remove these rows, then run the migration again."
        )

    op.execute(
        "CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS uq_users_email_lower;")
