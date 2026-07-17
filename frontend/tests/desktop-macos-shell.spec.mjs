import { test, expect } from '@playwright/test'

const apps = [
  {
    app_id: 'text-editor',
    name: '文本编辑器',
    icon: 'Edit',
    description: '编辑文本文件',
    entry_component_key: 'apps/text-editor/index.vue',
    default_width: 760,
    default_height: 520,
    min_width: 360,
    min_height: 260,
    category: '工具',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    supported_formats: ['txt', 'md'],
    editable_formats: ['txt', 'md'],
    allow_multiple: true,
    show_on_desktop: false,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
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

async function mockShell(page, { windows = [] } = {}) {
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
      return route.fulfill({ status: 200, json: { success: true, data: { user_id: 1, state_json: { version: 1, windows, appState: {}, iconPositions: {} }, version: 1 }, error: null } })
    }
    if (pathname.startsWith('/api/files/list')) {
      return route.fulfill({
        status: 200,
        json: {
          success: true,
          data: {
            items: [{ id: 501, name: 'Roadmap', extension: 'txt', is_folder: false, size: 128, created_at: '2026-07-17T10:00:00' }],
            total: 1,
            page: 1,
            page_size: 50,
          },
          error: null,
        },
      })
    }
    if (pathname === '/api/notifications/unread-count') {
      return route.fulfill({ status: 200, json: { success: true, data: { unread_count: 0 }, error: null } })
    }
    if (pathname === '/api/notifications') {
      return route.fulfill({ status: 200, json: { success: true, data: { list: [] }, error: null } })
    }
    if (pathname === '/api/tasks/worker/audit') {
      return route.fulfill({
        status: 200,
        json: {
          success: true,
          data: {
            summary: { pending: 0, running: 0, completed: 0, failed: 0 },
            recent_failed_count: 0,
            historical_debt_total: 0,
            classification: { recent_failed_count: 0, stale_pending_debt_count: 0, orphan_running_debt_count: 0, completed_semantic_failure_count: 0 },
          },
          error: null,
        },
      })
    }
    if (pathname === '/api/modules/call') {
      return route.fulfill({ status: 200, json: { success: true, data: { total: 0, items: [] }, error: null } })
    }
    if (pathname === '/api/knowledge/dashboard/stats') {
      return route.fulfill({ status: 200, json: { success: true, data: { source_unavailable_documents: 0, stuck_documents: [] }, error: null } })
    }
    if (pathname === '/api/knowledge/governance/pending-count') {
      return route.fulfill({ status: 200, json: { success: true, data: { pending_count: 0 }, error: null } })
    }
    return route.fulfill({ status: 200, json: { success: true, data: {}, error: null } })
  })
}

test('menus and system overlays restore focus and Spotlight indexes desktop files', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-file-icon-item[data-selection-key="file:501"]')).toBeVisible()

  const viewMenu = page.getByRole('button', { name: '查看' })
  await viewMenu.click()
  const menu = page.getByRole('menu')
  await expect(menu).toBeVisible()
  await expect(menu.getByRole('menuitem').first()).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(menu).toHaveCount(0)
  await expect(viewMenu).toBeFocused()

  const launchpadButton = page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '打开 Launchpad' })
  await launchpadButton.click()
  await expect(page.getByRole('dialog', { name: 'Launchpad' })).toBeVisible()
  await page.locator('.desktop-launcher-search-input').press('Escape')
  await expect(launchpadButton).toBeFocused()

  const spotlightButton = page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '打开 Spotlight' })
  await spotlightButton.click()
  await page.locator('.spotlight-input').fill('Roadmap')
  const fileResult = page.locator('.spotlight-result', { hasText: 'Roadmap.txt' })
  await expect(fileResult).toBeVisible()
  await expect(fileResult).toContainText('文件')
  await page.locator('.spotlight-input').press('Escape')
  await expect(spotlightButton).toBeFocused()
})

test('show desktop restores only windows hidden by that command', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '访达' })).toBeVisible()

  const result = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    const first = manager?.openWindow('desktop')
    const second = manager?.openWindow('text-editor', { fileId: 501, fileName: 'Roadmap.txt', format: 'txt' })
    if (!manager || !first || !second) return null
    manager.minimizeWindow(first)
    manager.showDesktop()
    const hidden = manager.windows.map(windowState => ({ id: windowState.id, minimized: windowState.minimized }))
    manager.restoreDesktop()
    const restored = manager.windows.map(windowState => ({ id: windowState.id, minimized: windowState.minimized }))
    return { first, second, hidden, restored }
  })

  expect(result).toBeTruthy()
  expect(result.hidden).toEqual(expect.arrayContaining([
    { id: result.first, minimized: true },
    { id: result.second, minimized: true },
  ]))
  expect(result.restored).toEqual(expect.arrayContaining([
    { id: result.first, minimized: true },
    { id: result.second, minimized: false },
  ]))
})

test('Dock groups multiple windows by app and exposes them in its app menu', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const dock = page.getByRole('navigation', { name: 'Dock' })
  await expect(dock.getByRole('button', { name: '访达' })).toBeVisible()

  const ids = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    return [
      manager?.openWindow('text-editor', { fileId: 501, fileName: 'Roadmap.txt', format: 'txt' }),
      manager?.openWindow('text-editor', { fileId: 502, fileName: 'Notes.txt', format: 'txt' }),
    ]
  })
  expect(ids.every(Boolean)).toBe(true)
  const textEditorButton = dock.getByRole('button', { name: '文本编辑器' })
  await expect(textEditorButton).toHaveCount(1)
  await textEditorButton.click({ button: 'right' })
  const appMenu = page.locator('.mac-dock-menu')
  await expect(appMenu).toBeVisible()
  await expect(appMenu.getByRole('menuitem')).toHaveCount(3)
})

test('desktop selection, context focus, and window drop feedback share one state', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const fileIcon = page.locator('.desktop-file-icon-item[data-selection-key="file:501"]')
  const appIcon = page.locator('.desktop-app-icon-item[data-selection-key="app:desktop"]')
  await expect(fileIcon).toBeVisible()

  await fileIcon.click()
  await appIcon.click({ modifiers: ['Meta'] })
  await expect(page.locator('.desktop-icon-item-selected')).toHaveCount(2)

  await page.mouse.click(100, 300)
  await expect(page.locator('.desktop-icon-item-selected')).toHaveCount(0)
  await fileIcon.click({ button: 'right' })
  await expect(fileIcon).toHaveClass(/desktop-icon-item-selected/)
  await expect(page.locator('.desktop-icon-item-selected')).toHaveCount(1)
  await page.keyboard.press('Escape')
  await expect(fileIcon).toBeFocused()

  await page.evaluate(() => window.__HSWZ_WINDOW_MANAGER__?.openWindow('desktop'))
  const window = page.locator('.desktop-window')
  await expect(window).toBeVisible()
  const fileBox = await fileIcon.boundingBox()
  const windowBox = await window.boundingBox()
  if (!fileBox || !windowBox) throw new Error('Desktop file or Finder window was not measurable')
  await page.mouse.move(fileBox.x + fileBox.width / 2, fileBox.y + fileBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(fileBox.x + fileBox.width / 2 - 10, fileBox.y + fileBox.height / 2 + 10, { steps: 3 })
  await page.mouse.move(windowBox.x + windowBox.width / 2, windowBox.y + windowBox.height / 2, { steps: 8 })
  await expect(window).toHaveClass(/desktop-window-drop-target/)
  await page.mouse.up()
  await expect(window).not.toHaveClass(/desktop-window-drop-target/)
})

test('restored sessions are clamped below MenuBar and above Dock', async ({ page }) => {
  await mockShell(page, {
    windows: [{
      id: 'legacy-window', appKey: 'desktop', title: '访达', icon: 'Folder',
      x: -400, y: -120, width: 2200, height: 1400, zIndex: 1,
      minimized: false, maximized: false, isActive: true, payload: {},
    }],
  })
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const restoredWindow = page.locator('.desktop-window')
  await expect(restoredWindow).toBeVisible()
  const box = await restoredWindow.boundingBox()
  expect(box?.x).toBeGreaterThanOrEqual(0)
  expect(box?.y).toBeGreaterThanOrEqual(24)
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(1025)
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(689)
})

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
    await expect(window).toHaveClass(/desktop-window-entered/)
    await expect.poll(async () => {
      const box = await window.boundingBox()
      return box ? box.x + box.width : null
    }).toBeLessThanOrEqual(viewport.width + 1)
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
