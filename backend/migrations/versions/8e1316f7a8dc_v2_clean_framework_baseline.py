"""v2_clean_framework_baseline

Revision ID: 8e1316f7a8dc
Revises: 
Create Date: 2026-06-17 23:23:26.776690

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '8e1316f7a8dc'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Tables without foreign key dependencies first
    op.create_table('framework_user_accounts',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False, comment='Login username'),
    sa.Column('password_hash', sa.String(length=256), nullable=False, comment='Bcrypt password hash'),
    sa.Column('display_name', sa.String(length=128), nullable=False, comment='Display name'),
    sa.Column('email', sa.String(length=128), nullable=True, comment='Email address'),
    sa.Column('role', sa.String(length=32), nullable=False, comment='admin / editor / viewer'),
    sa.Column('enabled', sa.Boolean(), nullable=False, comment='Whether account is active'),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True, comment='Last login time'),
    sa.Column('session_version', sa.Integer(), nullable=False, comment='Session version for invalidation'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('framework_app_registry',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=64), nullable=False, comment='Unique identifier, e.g. desktop, core-system, settings'),
    sa.Column('name', sa.String(length=128), nullable=False, comment='Display name'),
    sa.Column('app_type', sa.String(length=32), nullable=False, comment='builtin | custom'),
    sa.Column('description', sa.Text(), nullable=True, comment='App description'),
    sa.Column('route_prefix', sa.String(length=255), nullable=False, comment='API route prefix'),
    sa.Column('component_key', sa.String(length=128), nullable=False, comment='Frontend component key'),
    sa.Column('icon', sa.String(length=100), nullable=False, comment='Element Plus icon name'),
    sa.Column('category', sa.String(length=64), nullable=False, comment='Grouping category'),
    sa.Column('permissions', sa.JSON(), nullable=False, comment='Allowed roles: list of role names'),
    sa.Column('required_permission', sa.String(length=64), nullable=True, comment='Fine-grained permission key'),
    sa.Column('sort_order', sa.Integer(), nullable=False, comment='Display order, ascending'),
    sa.Column('default_width', sa.Integer(), nullable=False),
    sa.Column('default_height', sa.Integer(), nullable=False),
    sa.Column('min_width', sa.Integer(), nullable=False, comment='Minimum window width'),
    sa.Column('min_height', sa.Integer(), nullable=False, comment='Minimum window height'),
    sa.Column('singleton', sa.Boolean(), nullable=False, comment='Global singleton instance'),
    sa.Column('allow_multiple', sa.Boolean(), nullable=False, comment='Allow multiple instances'),
    sa.Column('resizable', sa.Boolean(), nullable=False),
    sa.Column('window_type', sa.String(length=32), nullable=False, comment='normal | tool | panel | fullscreen | background'),
    sa.Column('show_on_desktop', sa.Boolean(), nullable=False, comment='Show icon on desktop'),
    sa.Column('show_in_tray', sa.Boolean(), nullable=False, comment='Show in system tray'),
    sa.Column('show_in_launcher', sa.Boolean(), nullable=False, comment='Show in launcher / start menu'),
    sa.Column('show_in_sidebar', sa.Boolean(), nullable=False, comment='Show in right sidebar'),
    sa.Column('supported_formats', sa.JSON(), nullable=True, comment='Openable file extensions'),
    sa.Column('editable_formats', sa.JSON(), nullable=True, comment='Editable file extension subset'),
    sa.Column('enabled', sa.Boolean(), nullable=False, comment='Enabled / disabled'),
    sa.Column('needs_frontend_build', sa.Boolean(), nullable=False, comment='Requires npm build after update'),
    sa.Column('manifest_hash', sa.String(length=64), nullable=False, comment='Manifest file hash'),
    sa.Column('last_scan_time', sa.DateTime(timezone=True), nullable=True, comment='Last scan timestamp'),
    sa.Column('capabilities', sa.JSON(), nullable=True, comment='App capability declarations'),
    sa.Column('public_actions', sa.JSON(), nullable=True, comment='Public action declarations'),
    sa.Column('module_version', sa.String(length=32), nullable=False, comment='Module version'),
    sa.Column('contract_version', sa.String(length=32), nullable=False, comment='Manifest contract version'),
    sa.Column('installed_version', sa.String(length=32), nullable=True, comment='Installed version'),
    sa.Column('framework_min_version', sa.String(length=32), nullable=False, comment='Minimum framework version'),
    sa.Column('framework_max_version', sa.String(length=32), nullable=True, comment='Maximum framework version'),
    sa.Column('permission_declaration', sa.JSON(), nullable=True, comment='Permission declarations'),
    sa.Column('db_migration_declaration', sa.JSON(), nullable=True, comment='DB migration declarations'),
    sa.Column('event_handler_declaration', sa.JSON(), nullable=True, comment='Event handler declarations'),
    sa.Column('dependency_declaration', sa.JSON(), nullable=True, comment='Dependency declarations'),
    sa.Column('openable_types_declaration', sa.JSON(), nullable=True, comment='Openable file type declarations'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('framework_desktop_states',
    sa.Column('user_id', sa.BigInteger(), autoincrement=False, nullable=False, comment='User ID, FK to users.id'),
    sa.Column('state_json', sa.JSON(), nullable=False, comment='Desktop layout / window states JSON'),
    sa.Column('version', sa.Integer(), nullable=False, comment='Optimistic lock version'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('framework_role_matrices',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('role_key', sa.String(length=32), nullable=False, comment='admin / editor / viewer'),
    sa.Column('display_name', sa.String(length=64), nullable=False, comment='Display name for the role'),
    sa.Column('permissions', sa.JSON(), nullable=False, comment='Permission map, e.g. {"user_management": true, "system_config": false}'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('role_key')
    )
    op.create_table('framework_system_logs',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('level', sa.String(length=16), nullable=False),
    sa.Column('module', sa.String(length=64), nullable=False),
    sa.Column('action', sa.String(length=128), nullable=False),
    sa.Column('message', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('ip_address', sa.String(length=64), nullable=False),
    sa.Column('request_data', sa.JSON(), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_system_settings',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('key', sa.String(length=100), nullable=False),
    sa.Column('value', sa.Text(), nullable=False),
    sa.Column('description', sa.String(length=255), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('key')
    )
    op.create_table('framework_prompt_categories',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False, comment='Category name'),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('sort_order', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )

    # Tables that depend on framework_user_accounts
    op.create_table('framework_system_notifications',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=256), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('notification_type', sa.String(length=32), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('publisher_id', sa.Integer(), nullable=False),
    sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['publisher_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_system_task_queues',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('task_type', sa.String(length=64), nullable=False),
    sa.Column('parameters', sa.Text(), nullable=True),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.Integer(), nullable=False),
    sa.Column('module', sa.String(length=64), nullable=False),
    sa.Column('creator_id', sa.Integer(), nullable=True),
    sa.Column('retry_count', sa.Integer(), nullable=False),
    sa.Column('max_retries', sa.Integer(), nullable=False),
    sa.Column('error_message', sa.Text(), nullable=True),
    sa.Column('result', sa.Text(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_system_tasks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('title', sa.String(length=256), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('assignee_id', sa.Integer(), nullable=True),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('priority', sa.String(length=8), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['assignee_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_system_feedbacks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('feedback_type', sa.String(length=32), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('page_url', sa.Text(), nullable=False),
    sa.Column('user_agent', sa.String(length=512), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('admin_note', sa.Text(), nullable=True),
    sa.Column('handler_id', sa.Integer(), nullable=True),
    sa.Column('handled_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['handler_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # File system tables
    op.create_table('framework_file_folders',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False, comment='Folder name'),
    sa.Column('parent_id', sa.Integer(), nullable=True, comment='Parent folder id, null=root'),
    sa.Column('owner_id', sa.Integer(), nullable=False, comment='Creator'),
    sa.Column('deleted', sa.Boolean(), nullable=False, comment='Soft delete flag'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Time when soft deleted'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['owner_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['parent_id'], ['framework_file_folders.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_file_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('name', sa.String(length=256), nullable=False, comment='File name without extension'),
    sa.Column('extension', sa.String(length=32), nullable=False, comment='File extension, e.g. txt, pdf'),
    sa.Column('size', sa.BigInteger(), nullable=False, comment='File size in bytes'),
    sa.Column('folder_id', sa.Integer(), nullable=True, comment='Parent folder'),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('storage_path', sa.String(length=512), nullable=False, comment='Path on disk relative to storage root'),
    sa.Column('mime_type', sa.String(length=128), nullable=False, comment='MIME type'),
    sa.Column('md5_hash', sa.String(length=32), nullable=True, comment='MD5 hash'),
    sa.Column('ref_count', sa.Integer(), nullable=False, comment='Reference count for content dedup'),
    sa.Column('deleted', sa.Boolean(), nullable=False, comment='Soft delete flag'),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True, comment='Time when soft deleted'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['folder_id'], ['framework_file_folders.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['owner_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_file_recycle_items',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('origin_id', sa.Integer(), nullable=False, comment='Original file/folder id'),
    sa.Column('item_type', sa.String(length=16), nullable=False, comment='file or folder'),
    sa.Column('name', sa.String(length=256), nullable=False),
    sa.Column('owner_id', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['owner_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_file_shares',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('shared_by_owner_id', sa.Integer(), nullable=False),
    sa.Column('shared_with_user_id', sa.Integer(), nullable=False),
    sa.Column('permission', sa.String(length=16), nullable=False, comment='read | edit'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['file_id'], ['framework_file_items.id'], ),
    sa.ForeignKeyConstraint(['shared_by_owner_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['shared_with_user_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Remaining dependent tables
    op.create_table('framework_prompt_templates',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=True),
    sa.Column('name', sa.String(length=256), nullable=False, comment='Template name'),
    sa.Column('content', sa.Text(), nullable=False, comment='Prompt content with {{variable}} placeholders'),
    sa.Column('variables', postgresql.JSONB(astext_type=sa.Text()), nullable=True, comment='JSON array of variable names'),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('is_default', sa.Boolean(), nullable=False, comment='Mark as default template'),
    sa.Column('is_enabled', sa.Boolean(), nullable=False, comment='Soft enable/disable'),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['category_id'], ['framework_prompt_categories.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_table('framework_system_notification_reads',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('notification_id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['notification_id'], ['framework_system_notifications.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['framework_user_accounts.id'], ),
    sa.PrimaryKeyConstraint('id')
    )

    # Office JSON tables with circular FK: create packages without version FK first
    op.create_table('framework_file_json_packages',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False, comment='关联素材文件ID'),
    sa.Column('current_version_id', sa.Integer(), nullable=True),
    sa.Column('format_type', sa.String(length=32), nullable=False, comment='格式类型: docx/xlsx/pptx/txt/csv'),
    sa.Column('package_status', sa.String(length=32), nullable=False, comment='包状态: available/not_generated'),
    sa.Column('package_path', sa.String(length=512), nullable=False, comment='包存储路径'),
    sa.Column('summary', sa.Text(), nullable=True, comment='摘要'),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['file_id'], ['framework_file_items.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_file_json_versions',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('version_number', sa.Integer(), nullable=False, comment='版本号，自增'),
    sa.Column('json_content', sa.Text(), nullable=False, comment='JSON内容全文'),
    sa.Column('summary', sa.Text(), nullable=True, comment='版本摘要'),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['package_id'], ['framework_file_json_packages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    # Add the circular FK back now that versions table exists
    op.create_foreign_key(
        'fk_framework_file_json_packages_current_version',
        'framework_file_json_packages', 'framework_file_json_versions',
        ['current_version_id'], ['id']
    )
    op.create_table('framework_file_json_patches',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=False),
    sa.Column('source_version_id', sa.Integer(), nullable=False),
    sa.Column('target_version_id', sa.Integer(), nullable=False),
    sa.Column('operation_type', sa.String(length=64), nullable=False, comment='操作类型: replace_text/modify_cell/insert_image'),
    sa.Column('json_path', sa.String(length=512), nullable=False, comment='定位路径'),
    sa.Column('before_summary', sa.Text(), nullable=True, comment='修改前摘要'),
    sa.Column('after_content', sa.Text(), nullable=False, comment='修改后内容'),
    sa.Column('risk_level', sa.String(length=16), nullable=False, comment='风险等级: low/medium/high'),
    sa.Column('reason', sa.Text(), nullable=True, comment='修改原因'),
    sa.Column('patch_status', sa.String(length=32), nullable=False, comment='补丁状态: applied/pending_review/rejected'),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['package_id'], ['framework_file_json_packages.id'], ),
    sa.ForeignKeyConstraint(['source_version_id'], ['framework_file_json_versions.id'], ),
    sa.ForeignKeyConstraint(['target_version_id'], ['framework_file_json_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('framework_file_json_tasks',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('file_id', sa.Integer(), nullable=False),
    sa.Column('package_id', sa.Integer(), nullable=True),
    sa.Column('task_type', sa.String(length=64), nullable=False, comment='任务类型'),
    sa.Column('status', sa.String(length=32), nullable=False, comment='任务状态'),
    sa.Column('progress', sa.SmallInteger(), nullable=False, comment='进度 0-100'),
    sa.Column('error_message', sa.Text(), nullable=True, comment='错误信息'),
    sa.Column('creator_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Creation time'),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False, comment='Last update time'),
    sa.ForeignKeyConstraint(['creator_id'], ['framework_user_accounts.id'], ),
    sa.ForeignKeyConstraint(['file_id'], ['framework_file_items.id'], ),
    sa.ForeignKeyConstraint(['package_id'], ['framework_file_json_packages.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('framework_file_json_tasks')
    op.drop_table('framework_file_json_patches')
    op.execute('ALTER TABLE framework_file_json_packages DROP CONSTRAINT IF EXISTS fk_framework_file_json_packages_current_version')
    op.drop_table('framework_file_json_versions')
    op.drop_table('framework_file_json_packages')
    op.drop_table('framework_system_notification_reads')
    op.drop_table('framework_prompt_templates')
    op.drop_table('framework_file_shares')
    op.drop_table('framework_file_recycle_items')
    op.drop_table('framework_file_items')
    op.drop_table('framework_file_folders')
    op.drop_table('framework_system_feedbacks')
    op.drop_table('framework_system_tasks')
    op.drop_table('framework_system_task_queues')
    op.drop_table('framework_system_notifications')
    op.drop_table('framework_prompt_categories')
    op.drop_table('framework_system_settings')
    op.drop_table('framework_system_logs')
    op.drop_table('framework_role_matrices')
    op.drop_table('framework_desktop_states')
    op.drop_table('framework_app_registry')
    op.drop_table('framework_user_accounts')
