"""add_tools_called_to_chat_messages

Revision ID: d15000000001
Revises: d40000000001
Create Date: 2026-06-15 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'd15000000001'
down_revision: Union[str, Sequence[str], None] = 'd40000000001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('chat_messages', sa.Column('tools_called', postgresql.JSONB(), nullable=True, comment='本条消息调用的工具列表'))


def downgrade() -> None:
    op.drop_column('chat_messages', 'tools_called')
