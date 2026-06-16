"""add_email_last_login_session_version_and_role_matrix

Revision ID: 660a9bcb6d26
Revises: def987654321
Create Date: 2026-06-15 06:03:11.130275

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '660a9bcb6d26'
down_revision: Union[str, Sequence[str], None] = 'def987654321'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('email', sa.String(length=128), nullable=True, comment='Email address'))
    op.add_column('users', sa.Column('last_login', sa.DateTime(timezone=True), nullable=True, comment='Last login time'))
    op.add_column('users', sa.Column('session_version', sa.Integer(), server_default=sa.text('0'), nullable=False, comment='Session version for invalidation'))


def downgrade() -> None:
    op.drop_column('users', 'session_version')
    op.drop_column('users', 'last_login')
    op.drop_column('users', 'email')
