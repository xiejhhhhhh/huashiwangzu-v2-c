import type { MenuItemConfig } from './use-context-menu'

const openItem = (label: string, icon: string): MenuItemConfig => ({ key: 'open-app', label, icon })
const propertyItem: MenuItemConfig = { key: 'properties', label: '查看信息', icon: 'ⓘ' }

const iconMenuConfig: Record<string, (writable?: boolean, separatorItems?: () => MenuItemConfig[], buildRecycleMenu?: (writable?: boolean) => MenuItemConfig[]) => MenuItemConfig[]> = {
  recycle: (writable, _separatorItems, buildRecycleMenu) => buildRecycleMenu!(writable),
  desktop: (writable, separatorItems) => [
    openItem('打开', '📂'),
    ...separatorItems!(),
    { key: 'upload-file', label: '添加文件', icon: '⬆', disabled: !writable },
    { key: 'create-folder', label: '添加文件夹', icon: '📁', disabled: !writable },
  ],
  settings: (_writable, separatorItems) => [openItem('打开', '⚙️'), ...separatorItems!(), propertyItem],
  tasks: (_writable, separatorItems) => [openItem('打开', '✅'), ...separatorItems!(), propertyItem],
}

export function buildDesktopShellBlankMenu(separatorItems: () => MenuItemConfig[]): MenuItemConfig[] {
  return [
    { key: 'view', label: '查看', icon: '⊞', children: [{ key: 'view-medium-icons', label: '中等图标', icon: '▦' }, { key: 'view-auto-arrange', label: '自动排列图标', icon: '⋮' }, { key: 'view-align-grid', label: '对齐网格', icon: '⌗' }] },
    { key: 'sort-by', label: '排序方式', icon: '⇅', children: [{ key: 'sort-name', label: '名称' }, { key: 'sort-type', label: '项目类型' }, { key: 'sort-date', label: '修改日期' }] },
    { key: 'new-folder', label: '新建文件夹', icon: '📁' },
    { key: 'refresh-desktop', label: '刷新', icon: '↻' },
  ]
}

export function buildDesktopShellIconMenu(appKey: string, writable?: boolean, separatorItems?: () => MenuItemConfig[], buildRecycleMenu?: (writable?: boolean) => MenuItemConfig[]): MenuItemConfig[] {
  return iconMenuConfig[appKey]?.(writable, separatorItems, buildRecycleMenu) ?? []
}
