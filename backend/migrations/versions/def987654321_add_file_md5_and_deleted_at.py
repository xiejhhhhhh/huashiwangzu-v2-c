"""add_file_md5_and_deleted_at

Revision ID: def987654321
Revises: abc123456789
Create Date: 2026-06-15 06:02:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'def987654321'
down_revision: Union[str, Sequence[str], None] = 'abc123456789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('files', sa.Column('md5', sa.String(length=64), nullable=True, comment='MD5 hash'))
    op.add_column('files', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Time when soft deleted'))


def downgrade() -> None:
    op.drop_column('files', 'deleted_at')
    op.drop_column('files', 'md5')
