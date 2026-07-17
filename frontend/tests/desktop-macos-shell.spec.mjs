import { test, expect } from '@playwright/test'

const apps = [
  {
    app_id: 'desktop',
    name: '访达',
    icon: 'Folder',
    description: '管理桌面文件',
    entry_component_key: 'apps/desktop/index.vue',
    default_width: 820,
    default_height: 560,
    min_width: 360,
    min_height: 260,
    category: '系统',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    app_id: 'desktop-tools',
    name: 'Desktop Tools',
    icon: 'Connection',
    description: '后台文件桥接能力',
    entry_component_key: '',
    default_width: 800,
    default_height: 600,
    category: '后台能力',
    window_type: 'background-service',
    permissions: ['viewer', 'editor', 'admin'],
    show_on_desktop: false,
    show_in_launcher: false,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
]

async function mockShell(page) {
  await page.addInitScript(() => localStorage.setItem('v2_auth_token', 'macos-shell-test-token'))
  await page.route(/^https?:\/\/[^/]+\/api\/.*/, route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/current-user') {
      return route.fulfill({ status: 200, json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null } })
    }
    if (pathname === '/api/desktop/apps') {
      return route.fulfill({ status: 200, json: { success: true, data: apps, error: null } })
    }
    if (pathname === '/api/desktop/state') {
      return route.fulfill({ status: 200, json: { success: true, data: { user_id: 1, state_json: { version: 1, windows: [], appState: {}, iconPositions: {} }, version: 1 }, error: null } })
    }
    if (pathname.startsWith('/api/files/list')) {
      return route.fulfill({ status: 200, json: { success: true, data: { items: [], total: 0, page: 1, page_size: 50 }, error: null } })
    }
    if (pathname === '/api/notifications/unread-count') {
      return route.fulfill({ status: 200, json: { success: true, data: { unread_count: 0 }, error: null } })
    }
    if (pathname === '/api/notifications') {
      return route.fulfill({ status: 200, json: { success: true, data: { list: [] }, error: null } })
    }
    return route.fulfill({ status: 200, json: { success: true, data: {}, error: null } })
  })
}

const viewports = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'compact', width: 1024, height: 720 },
  { name: 'mobile', width: 390, height: 844 },
]

for (const viewport of viewports) {
  test(`macOS shell contract remains coherent at ${viewport.name} viewport`, async ({ page }) => {
    await mockShell(page)
    await page.setViewportSize({ width: viewport.width, height: viewport.height })
    await page.goto('/desktop', { waitUntil: 'domcontentloaded' })

    const menuBar = page.getByRole('banner', { name: '系统菜单栏' })
    const dock = page.getByRole('navigation', { name: 'Dock' })
    await expect(menuBar).toBeVisible()
    await expect(dock).toBeVisible()
    await expect(page.locator('.taskbar-window-button')).toHaveCount(0)

    const menuBox = await menuBar.boundingBox()
    const dockBox = await dock.boundingBox()
    expect(menuBox?.height).toBe(24)
    expect(dockBox?.y).toBeGreaterThanOrEqual(viewport.height - 80)
    expect((dockBox?.x ?? 0) + (dockBox?.width ?? 0)).toBeLessThanOrEqual(viewport.width + 1)

    await dock.getByRole('button', { name: '打开 Launchpad' }).click()
    await expect(page.getByRole('dialog', { name: 'Launchpad' })).toBeVisible()
    await expect(page.locator('.desktop-launcher-app-item', { hasText: '访达' })).toBeVisible()
    await expect(page.locator('.desktop-launcher-app-item', { hasText: 'Desktop Tools' })).toHaveCount(0)
    await page.locator('.desktop-launcher-search-input').press('Escape')

    await page.keyboard.press('Control+Space')
    await expect(page.getByRole('dialog', { name: 'Spotlight' })).toBeVisible()
    await page.locator('.spotlight-input').fill('Desktop Tools')
    await expect(page.locator('.spotlight-result', { hasText: 'Desktop Tools' })).toContainText('后台能力')
    await page.locator('.spotlight-input').press('Escape')

    await page.evaluate(() => window.__HSWZ_WINDOW_MANAGER__?.openWindow('desktop'))
    const window = page.locator('.desktop-window')
    await expect(window).toBeVisible()
    const windowBox = await window.boundingBox()
    expect(windowBox?.x).toBeGreaterThanOrEqual(0)
    expect(windowBox?.y).toBeGreaterThanOrEqual(24)
    expect((windowBox?.x ?? 0) + (windowBox?.width ?? 0)).toBeLessThanOrEqual(viewport.width + 1)
    expect((windowBox?.y ?? 0) + (windowBox?.height ?? 0)).toBeLessThanOrEqual(viewport.height - 79)

    const controls = window.locator('.window-action-buttons button')
    await expect(controls).toHaveCount(3)
    await expect(controls.nth(0)).toHaveAttribute('aria-label', '关闭')
    await expect(controls.nth(1)).toHaveAttribute('aria-label', '最小化')
    await expect(controls.nth(2)).toHaveAttribute('aria-label', '缩放')
  })
}
