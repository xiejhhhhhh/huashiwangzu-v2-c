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
    {
      key: 'view',
      label: '查看',
      icon: '⊞',
      children: [
        { key: 'view-auto-arrange', label: '自动排列图标', icon: '⋮' },
        { key: 'view-free-arrange', label: '自由排列', icon: '▦' },
        { key: 'view-align-grid', label: '对齐到网格', icon: '⌗' },
        { key: 'toggle-icon-labels', label: '显示图标标签', icon: '🏷' },
      ],
    },
    {
      key: 'sort-by',
      label: '排序方式',
      icon: '⇅',
      children: [
        { key: 'sort-name', label: '名称', icon: '' },
        { key: 'sort-type', label: '项目类型', icon: '' },
        { key: 'sort-date', label: '修改日期', icon: '' },
      ],
    },
    {
      key: 'wallpaper',
      label: '更换壁纸',
      icon: '🖼',
      children: [
        { key: 'wallpaper-default', label: '默认 macOS', icon: '' },
        { key: 'wallpaper-gradient-dusk', label: '暮色渐变', icon: '' },
        { key: 'wallpaper-gradient-ocean', label: '海洋渐变', icon: '' },
        { key: 'wallpaper-solid-dark', label: '深空黑', icon: '' },
      ],
    },
    ...separatorItems(),
    { key: 'new-folder', label: '新建文件夹', icon: '📁' },
    { key: 'open-desktop-file-manager', label: '打开访达', icon: '📂' },
    { key: 'refresh-desktop', label: '刷新', icon: '↻' },
  ]
}

export function buildDesktopShellIconMenu(appKey: string, writable?: boolean, separatorItems?: () => MenuItemConfig[], buildRecycleMenu?: (writable?: boolean) => MenuItemConfig[]): MenuItemConfig[] {
  return iconMenuConfig[appKey]?.(writable, separatorItems, buildRecycleMenu) ?? []
}
