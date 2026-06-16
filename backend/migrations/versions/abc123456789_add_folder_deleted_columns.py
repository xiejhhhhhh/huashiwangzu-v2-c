"""add_folder_deleted_columns

Revision ID: abc123456789
Revises: d79ddd6b00e1
Create Date: 2026-06-15 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'abc123456789'
down_revision: Union[str, Sequence[str], None] = '8448fc2d93d9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('folders', sa.Column('deleted', sa.Boolean(), server_default=sa.text('false'), nullable=False, comment='Soft delete flag'))
    op.add_column('folders', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Time when soft deleted'))
    op.create_index('ix_folders_deleted', 'folders', ['deleted'])


def downgrade() -> None:
    op.drop_index('ix_folders_deleted', table_name='folders')
    op.drop_column('folders', 'deleted_at')
    op.drop_column('folders', 'deleted')
