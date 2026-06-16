"""add_app_fields_and_desktop_states

Revision ID: 9a8b7c6d5e4f
Revises: 660a9bcb6d26
Create Date: 2026-06-15 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '9a8b7c6d5e4f'
down_revision: Union[str, Sequence[str], None] = '660a9bcb6d26'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add columns to apps table
    op.add_column('apps', sa.Column('app_type', sa.String(length=32), nullable=False, server_default='builtin', comment='builtin | custom'))
    op.add_column('apps', sa.Column('window_type', sa.String(length=32), nullable=False, server_default='normal', comment='normal | tool | panel | fullscreen | background'))
    op.add_column('apps', sa.Column('min_width', sa.Integer(), nullable=False, server_default='400', comment='Minimum window width'))
    op.add_column('apps', sa.Column('min_height', sa.Integer(), nullable=False, server_default='300', comment='Minimum window height'))
    op.add_column('apps', sa.Column('allow_multiple', sa.Boolean(), nullable=False, server_default='false', comment='Allow multiple instances'))
    op.add_column('apps', sa.Column('show_on_desktop', sa.Boolean(), nullable=False, server_default='false', comment='Show icon on desktop'))
    op.add_column('apps', sa.Column('show_in_tray', sa.Boolean(), nullable=False, server_default='false', comment='Show in system tray'))
    op.add_column('apps', sa.Column('show_in_launcher', sa.Boolean(), nullable=False, server_default='true', comment='Show in launcher / start menu'))
    op.add_column('apps', sa.Column('show_in_sidebar', sa.Boolean(), nullable=False, server_default='false', comment='Show in right sidebar'))
    op.add_column('apps', sa.Column('supported_formats', postgresql.JSONB, nullable=True, comment='Openable file extensions'))
    op.add_column('apps', sa.Column('editable_formats', postgresql.JSONB, nullable=True, comment='Editable file extension subset'))
    op.add_column('apps', sa.Column('needs_frontend_build', sa.Boolean(), nullable=False, server_default='false', comment='Requires npm build'))
    op.add_column('apps', sa.Column('manifest_hash', sa.String(length=64), nullable=False, server_default='', comment='Manifest file hash'))
    op.add_column('apps', sa.Column('last_scan_time', sa.DateTime(timezone=True), nullable=True, comment='Last scan timestamp'))
    op.add_column('apps', sa.Column('capabilities', postgresql.JSONB, nullable=True, comment='App capability declarations'))
    op.add_column('apps', sa.Column('public_actions', postgresql.JSONB, nullable=True, comment='Public action declarations'))
    op.add_column('apps', sa.Column('module_version', sa.String(length=32), nullable=False, server_default='1.0.0', comment='Module version'))
    op.add_column('apps', sa.Column('contract_version', sa.String(length=32), nullable=False, server_default='2.0', comment='Manifest contract version'))
    op.add_column('apps', sa.Column('installed_version', sa.String(length=32), nullable=True, comment='Installed version'))
    op.add_column('apps', sa.Column('framework_min_version', sa.String(length=32), nullable=False, server_default='1.0.0', comment='Min framework version'))
    op.add_column('apps', sa.Column('framework_max_version', sa.String(length=32), nullable=True, comment='Max framework version'))
    op.add_column('apps', sa.Column('permission_declaration', postgresql.JSONB, nullable=True, comment='Permission declarations'))
    op.add_column('apps', sa.Column('db_migration_declaration', postgresql.JSONB, nullable=True, comment='DB migration declarations'))
    op.add_column('apps', sa.Column('event_handler_declaration', postgresql.JSONB, nullable=True, comment='Event handler declarations'))
    op.add_column('apps', sa.Column('dependency_declaration', postgresql.JSONB, nullable=True, comment='Dependency declarations'))
    op.add_column('apps', sa.Column('openable_types_declaration', postgresql.JSONB, nullable=True, comment='Openable file type declarations'))
    op.alter_column('apps', 'route_prefix',
                    existing_type=sa.String(length=64),
                    type_=sa.String(length=255),
                    existing_nullable=False,
                    existing_server_default=sa.text("''::character varying"))
    op.alter_column('apps', 'icon',
                    existing_type=sa.String(length=64),
                    type_=sa.String(length=100),
                    existing_nullable=False,
                    existing_server_default=sa.text("'Collection'::character varying"))

    # Create desktop_states table
    op.create_table('desktop_states',
        sa.Column('user_id', sa.BigInteger(), nullable=False, comment='User ID, FK to users.id'),
        sa.Column('state_json', postgresql.JSONB, nullable=False, comment='Desktop layout / window states JSON'),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1', comment='Optimistic lock version'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
        sa.PrimaryKeyConstraint('user_id'),
    )


def downgrade() -> None:
    op.drop_table('desktop_states')
    op.alter_column('apps', 'icon',
                    existing_type=sa.String(length=100),
                    type_=sa.String(length=64),
                    existing_nullable=False,
                    existing_server_default=sa.text("'Collection'::character varying"))
    op.alter_column('apps', 'route_prefix',
                    existing_type=sa.String(length=255),
                    type_=sa.String(length=64),
                    existing_nullable=False,
                    existing_server_default=sa.text("''::character varying"))
    op.drop_column('apps', 'openable_types_declaration')
    op.drop_column('apps', 'dependency_declaration')
    op.drop_column('apps', 'event_handler_declaration')
    op.drop_column('apps', 'db_migration_declaration')
    op.drop_column('apps', 'permission_declaration')
    op.drop_column('apps', 'framework_max_version')
    op.drop_column('apps', 'framework_min_version')
    op.drop_column('apps', 'installed_version')
    op.drop_column('apps', 'contract_version')
    op.drop_column('apps', 'module_version')
    op.drop_column('apps', 'public_actions')
    op.drop_column('apps', 'capabilities')
    op.drop_column('apps', 'last_scan_time')
    op.drop_column('apps', 'manifest_hash')
    op.drop_column('apps', 'needs_frontend_build')
    op.drop_column('apps', 'editable_formats')
    op.drop_column('apps', 'supported_formats')
    op.drop_column('apps', 'show_in_sidebar')
    op.drop_column('apps', 'show_in_launcher')
    op.drop_column('apps', 'show_in_tray')
    op.drop_column('apps', 'show_on_desktop')
    op.drop_column('apps', 'allow_multiple')
    op.drop_column('apps', 'min_height')
    op.drop_column('apps', 'min_width')
    op.drop_column('apps', 'window_type')
    op.drop_column('apps', 'app_type')
