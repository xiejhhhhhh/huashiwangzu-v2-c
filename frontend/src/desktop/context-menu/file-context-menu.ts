import type { MenuItemConfig } from './use-context-menu'
import { hasContent } from '@/desktop/clipboard/clipboard-state'
import { FINDER_TAGS, type FinderTagColor } from '@/platform/components/apps/desktop/file-manager/finder-tags'

function viewSubItems(_separatorItems: () => MenuItemConfig[]) {
  return [{ key: 'view-list', label: '列表', icon: '≣' }, { key: 'view-icons', label: '图标', icon: '▦' }]
}

function buildTagMenuChildren(activeTags: FinderTagColor[] = []): MenuItemConfig[] {
  const active = new Set(activeTags)
  return [
    ...FINDER_TAGS.map((tag) => ({
      key: `tag:${tag.key}`,
      label: active.has(tag.key) ? `✓ ${tag.name}` : tag.name,
      icon: '●',
    })),
    { key: 'sep-tag-clear', label: '', separator: true },
    { key: 'tag:clear', label: '移除全部标签', icon: '○' },
  ]
}

export function buildFileMenu(
  writable: boolean,
  separatorItems: () => MenuItemConfig[],
  activeTags: FinderTagColor[] = [],
): MenuItemConfig[] {
  return [
    { key: 'open', label: '打开', icon: '↗' },
    { key: 'download', label: '下载到本地', icon: '⬇' },
    ...separatorItems(),
    ...(writable
      ? [
          { key: 'cut', label: '剪切', icon: '✂' },
          { key: 'copy', label: '复制', icon: '📋' },
          { key: 'duplicate', label: '制作副本', icon: '❐' },
        ]
      : []),
    { key: 'copy-path', label: '复制路径', icon: '⎘' },
    {
      key: 'tags',
      label: '标签',
      icon: '🏷',
      children: buildTagMenuChildren(activeTags),
    },
    { key: 'details', label: '显示简介', icon: 'ⓘ' },
    ...(writable
      ? [
          ...separatorItems(),
          { key: 'compress', label: '压缩', icon: '📦' },
          { key: 'rename', label: '重命名', icon: '✎' },
          { key: 'delete', label: '删除', icon: '🗑', danger: true },
        ]
      : []),
  ]
}

export function buildFolderMenu(
  writable: boolean,
  separatorItems: () => MenuItemConfig[],
  activeTags: FinderTagColor[] = [],
): MenuItemConfig[] {
  return [
    { key: 'open', label: '打开', icon: '📂' },
    { key: 'open-in-new-window', label: '在新窗口中打开', icon: '⧉' },
    { key: 'upload-here', label: '上传文件', icon: '⬆', disabled: !writable },
    { key: 'create-folder-here', label: '新建文件夹', icon: '+', disabled: !writable },
    ...separatorItems(),
    ...(writable
      ? [
          { key: 'cut', label: '剪切', icon: '✂' },
          { key: 'copy', label: '复制', icon: '📋' },
          { key: 'duplicate', label: '制作副本', icon: '❐' },
        ]
      : []),
    { key: 'copy-path', label: '复制路径', icon: '⎘' },
    {
      key: 'tags',
      label: '标签',
      icon: '🏷',
      children: buildTagMenuChildren(activeTags),
    },
    { key: 'details', label: '显示简介', icon: 'ⓘ' },
    ...(writable && hasContent.value ? [...separatorItems(), { key: 'paste-here', label: '粘贴', icon: '📌' }] : []),
    ...(writable
      ? [
          ...separatorItems(),
          { key: 'compress', label: '压缩', icon: '📦' },
          { key: 'rename', label: '重命名', icon: '✎' },
          { key: 'delete', label: '删除', icon: '🗑', danger: true },
        ]
      : []),
  ]
}

export function buildDesktopBlankMenu(writable: boolean, separatorItems: () => MenuItemConfig[]): MenuItemConfig[] {
  const sortSubItems = [{ key: 'sort-name', label: '名称' }, { key: 'sort-type', label: '项目类型' }, { key: 'sort-date', label: '修改日期' }]
  return [
    { key: 'view', label: '查看', icon: '⊞', children: viewSubItems(separatorItems) },
    { key: 'sort-by', label: '排序方式', icon: '⇅', children: sortSubItems },
    ...(writable && hasContent.value ? [{ key: 'paste', label: '粘贴', icon: '📌' }, ...separatorItems()] : []),
    { key: 'upload-file', label: '上传文件', icon: '⬆', disabled: !writable },
    { key: 'create-folder', label: '新建文件夹', icon: '+', disabled: !writable },
    { key: 'refresh', label: '刷新', icon: '↻' },
  ]
}


export function buildMultiSelectMenu(
  writable: boolean,
  separatorItems: () => MenuItemConfig[],
  count: number,
  activeTags: FinderTagColor[] = [],
): MenuItemConfig[] {
  const label = count > 1 ? `已选 ${count} 项` : '已选 1 项'
  return [
    { key: 'selection-info', label, icon: '☑', disabled: true },
    ...separatorItems(),
    ...(writable
      ? [
          { key: 'cut', label: '剪切', icon: '✂' },
          { key: 'copy', label: '复制', icon: '📋' },
          { key: 'duplicate', label: '制作副本', icon: '❐' },
          { key: 'compress', label: '压缩', icon: '📦' },
        ]
      : []),
    {
      key: 'tags',
      label: '标签',
      icon: '🏷',
      children: buildTagMenuChildren(activeTags),
    },
    ...(writable ? [...separatorItems(), { key: 'delete', label: '删除', icon: '🗑', danger: true }] : []),
  ]
}

export function buildArrangeMenu(active: 'none' | 'kind' | 'date' = 'none'): MenuItemConfig[] {
  const mark = (mode: string, label: string) => ({
    key: `group-by:${mode}`,
    label: active === mode ? `✓ ${label}` : label,
    icon: '☰',
  })
  return [
    mark('none', '不分组'),
    mark('kind', '按种类'),
    mark('date', '按修改日期'),
  ]
}

export function buildFolderTreeNodeMenu(writable: boolean, separatorItems: () => MenuItemConfig[]): MenuItemConfig[] {
  return [
    { key: 'open', label: '打开', icon: '📂' },
    { key: 'upload-here', label: '上传文件', icon: '⬆', disabled: !writable },
    { key: 'create-folder-here', label: '新建文件夹', icon: '+', disabled: !writable },
    ...separatorItems(),
    ...(writable ? [{ key: 'cut', label: '剪切', icon: '✂' }, { key: 'copy', label: '复制', icon: '📋' }] : []),
    { key: 'copy-path', label: '复制路径', icon: '⎘' },
    ...(writable && hasContent.value ? [{ key: 'paste-here', label: '粘贴', icon: '📌' }] : []),
    ...(writable ? [...separatorItems(), { key: 'rename', label: '重命名', icon: '✎' }, { key: 'delete', label: '删除', icon: '🗑', danger: true }] : []),
  ]
}

export function buildRecycleBinMenu(writable = false, separatorItems: () => MenuItemConfig[]): MenuItemConfig[] {
  return [{ key: 'open-recycle-bin', label: '打开回收站', icon: '🗑' }, ...(writable ? [...separatorItems(), { key: 'empty-recycle-bin', label: '清空回收站', icon: '🧹', danger: true }] : [])]
}

export function buildRecycleBinItemMenu(writable: boolean): MenuItemConfig[] {
  return writable ? [{ key: 'restore', label: '还原', icon: '↩' }, { key: 'delete-permanently', label: '彻底删除', icon: '🗑', danger: true }] : []
}
