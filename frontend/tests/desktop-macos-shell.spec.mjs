import { test, expect } from '@playwright/test'

const apps = [
  {
    product_id: 'text',
    name: '文本',
    icon: 'Edit',
    description: '编辑文本文件',
    entry_component_key: 'text-editor/index.vue',
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
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    product_id: 'files',
    name: '文件',
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
    allow_multiple: true,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    product_id: 'background-tools',
    name: '后台工具',
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
  {
    product_id: 'office',
    name: 'Office',
    icon: 'Document',
    description: '统一文档工作区',
    entry_component_key: 'products/office/frontend/index.vue',
    default_width: 1100,
    default_height: 760,
    min_width: 480,
    min_height: 320,
    category: '办公',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: true,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    product_id: 'knowledge',
    name: '知识库',
    icon: 'Collection',
    description: '知识检索与工作台',
    entry_component_key: 'knowledge/index.vue',
    default_width: 1100,
    default_height: 760,
    min_width: 480,
    min_height: 320,
    category: '知识',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: false,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    product_id: 'ai',
    name: 'AI',
    icon: 'ChatDotRound',
    description: '智能体对话',
    entry_component_key: 'agent/index.vue',
    default_width: 1080,
    default_height: 760,
    min_width: 480,
    min_height: 320,
    category: 'AI',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: true,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    product_id: 'settings',
    name: '设置',
    icon: 'Setting',
    description: '系统与个人偏好设置',
    entry_component_key: 'apps/settings/index.vue',
    default_width: 860,
    default_height: 640,
    min_width: 480,
    min_height: 320,
    category: '系统',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: false,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
]

function productCatalog() {
  return {
    catalogRevision: 'test',
    count: apps.length,
    kind: 'products',
    items: apps.map(app => ({
      productId: app.product_id,
      displayName: app.name,
      icon: app.icon,
      description: app.description,
      entryComponentKey: app.entry_component_key,
      visibility: { desktop: app.show_on_desktop, launcher: app.show_in_launcher, dock: app.show_on_desktop },
      windowPolicy: { defaultWidth: app.default_width, defaultHeight: app.default_height, minWidth: app.min_width, minHeight: app.min_height, singleton: !app.allow_multiple, allowMultiple: app.allow_multiple },
      enabled: app.enabled,
      allowMultiple: app.allow_multiple,
      legacyAppKeys: app.product_id === 'files' ? ['desktop'] : app.product_id === 'text' ? ['text-editor'] : app.product_id === 'ai' ? ['agent'] : app.product_id === 'knowledge' ? ['knowledge'] : [],
      sortOrder: app.product_id === 'files' ? 10 : 20,
      uiContract: app.ui_contract || {
        kit: 'mac-app-v1',
        layout: app.product_id === 'files' || app.product_id === 'knowledge' || app.product_id === 'recycle' ? 'finder'
          : app.product_id === 'ai' || app.product_id === 'messages' ? 'chat'
          : app.product_id === 'settings' ? 'settings'
          : app.product_id === 'office' || app.product_id === 'text' || app.product_id === 'content-studio' ? 'document'
          : 'utility',
        shell: { useAppWindowFrame: true },
        feedback: 'desktop-kit',
        density: 'comfortable',
      },
    })),
  }
}

async function mockShell(page, { windows = [] } = {}) {
  await page.addInitScript(() => localStorage.setItem('v2_auth_token', 'macos-shell-test-token'))
  await page.route(/^https?:\/\/[^/]+\/api\/.*/, route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/current-user') {
      return route.fulfill({ status: 200, json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null } })
    }
    if (pathname === '/api/desktop/products') {
      return route.fulfill({ status: 200, json: { success: true, data: productCatalog(), error: null } })
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
  const launchpad = page.getByRole('dialog', { name: 'Launchpad' })
  await expect(launchpad).toBeVisible()
  await expect(launchpad.locator('.desktop-launcher-app-item', { hasText: '文件' })).toBeVisible()
  await expect(launchpad.locator('.desktop-launcher-app-item', { hasText: '文本' })).toBeVisible()
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
  await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '文件' })).toBeVisible()

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

test('Liquid Glass primitives and Dock neighbor magnification are wired', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })

  const menuBar = page.getByRole('banner', { name: '系统菜单栏' })
  const dock = page.getByRole('navigation', { name: 'Dock' })
  await expect(menuBar).toHaveClass(/glass-menubar/)
  await expect(dock).toHaveClass(/glass-dock/)
  await expect(page.locator('#desktop-liquid-refraction')).toHaveCount(1)
  await page.getByRole('button', { name: '打开控制中心' }).click()
  await expect(page.getByRole('dialog', { name: '控制中心' })).toBeVisible()
  await expect(page.getByRole('dialog', { name: '控制中心' })).toContainText('无线局域网')
  await page.mouse.click(20, 200)

  await page.evaluate(() => window.__HSWZ_WINDOW_MANAGER__?.openWindow('desktop'))
  const windowFrame = page.locator('.desktop-window')
  await expect(windowFrame).toHaveClass(/glass-window/)
  await expect(windowFrame).toHaveClass(/desktop-window-active/)

  const filesButton = dock.getByRole('button', { name: '文件' })
  await expect(filesButton).toBeVisible()
  await filesButton.hover()
  await expect(page.locator('.mac-dock-item-wrap.is-hovered')).toHaveCount(1)
  await expect(page.locator('.mac-dock-item-wrap.is-neighbor')).toHaveCount(2)

  await dock.getByRole('button', { name: '打开 Spotlight' }).click()
  await expect(page.locator('.spotlight-panel')).toHaveClass(/glass-spotlight/)
  await page.locator('.spotlight-input').press('Escape')
})

test('Dock groups multiple windows by app and exposes them in its app menu', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const dock = page.getByRole('navigation', { name: 'Dock' })
  await expect(dock.getByRole('button', { name: '文件' })).toBeVisible()

  const ids = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    return [
      manager?.openWindow('text-editor', { fileId: 501, fileName: 'Roadmap.txt', format: 'txt' }),
      manager?.openWindow('text-editor', { fileId: 502, fileName: 'Notes.txt', format: 'txt' }),
    ]
  })
  expect(ids.every(Boolean)).toBe(true)
  const textEditorButton = dock.getByRole('button', { name: '文本' })
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
  const appIcon = page.locator('.desktop-app-icon-item[data-selection-key="app:files"]')
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
      id: 'legacy-window', appKey: 'desktop', title: '文件', icon: 'Folder',
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
  expect(box?.y).toBeGreaterThanOrEqual(28)
  expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(1025)
  expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(689)
})


test('App Switcher cycles open windows with meta-tab semantics', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '文件' })).toBeVisible()
  const opened = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    // open two files windows (allowMultiple) to avoid missing text-editor loader in mocks
    return [
      manager?.openWindow('files', { folderId: 0 }),
      manager?.openWindow('files', { folderId: 1, folderName: '文档' }),
    ]
  })
  expect(opened.filter(Boolean).length).toBeGreaterThanOrEqual(2)
  await expect.poll(async () => page.evaluate(() => (window.__HSWZ_WINDOW_MANAGER__?.windows || []).filter(w => !w.minimized).length)).toBeGreaterThanOrEqual(2)
  await expect.poll(async () => page.evaluate(() => Boolean(window.__HSWZ_DESKTOP_SHELL__?.openAppSwitcher))).toBe(true)
  await page.evaluate(() => window.__HSWZ_DESKTOP_SHELL__?.openAppSwitcher())
  const switcher = page.getByRole('dialog', { name: 'App Switcher' })
  await expect(switcher).toBeVisible()
  await expect(switcher.locator('.app-switcher-item')).toHaveCount(2)
  await page.evaluate(() => window.__HSWZ_DESKTOP_SHELL__?.closeAppSwitcher())
  await expect(switcher).toHaveCount(0)
})




test('app icons expose material layers for Dock and titlebar sizes', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const dockIcon = page.getByRole('navigation', { name: 'Dock' }).locator('.app-icon').first()
  await expect(dockIcon.locator('.app-icon-base')).toBeVisible()
  await expect(dockIcon.locator('.app-icon-sheen')).toBeVisible()
  await page.evaluate(() => window.__HSWZ_WINDOW_MANAGER__?.openWindow('desktop'))
  const titleIcon = page.locator('.desktop-window .app-icon').first()
  await expect(titleIcon).toHaveClass(/app-icon-sm/)
  await expect(titleIcon.locator('.app-icon-rim')).toBeVisible()
})

test('mac wallpaper asset and glass recipe vars are active', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  const wallpaper = page.locator('.desktop-shell-wallpaper')
  await expect(wallpaper).toBeVisible()
  await expect.poll(async () => wallpaper.evaluate(el => getComputedStyle(el).backgroundImage)).toContain('wallpaper-macos-default.svg')
  const filter = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--desktop-lg-filter').trim())
  expect(filter).toContain('blur(34px)')
  await page.getByRole('button', { name: '打开控制中心' }).click()
  const cc = page.getByRole('dialog', { name: '控制中心' })
  await expect(cc).toBeVisible()
  const radius = await cc.evaluate(el => getComputedStyle(el).borderRadius)
  expect(radius === '22px' || radius.startsWith('22')).toBeTruthy()
})

test('shell skin contract applies macos tokens and can switch to win11 slot', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect.poll(async () => page.evaluate(() => document.documentElement.dataset.desktopSkin)).toBe('macos')
  const menuH = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--desktop-menu-bar-height').trim())
  expect(menuH).toBe('28px')
  await page.evaluate(() => window.__HSWZ_DESKTOP_SHELL__?.setShellSkin?.('win11'))
  await expect.poll(async () => page.evaluate(() => document.documentElement.dataset.desktopSkin)).toBe('win11')
  const dockRadius = await page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--desktop-dock-radius').trim())
  expect(dockRadius).toBe('0px')
  await page.evaluate(() => window.__HSWZ_DESKTOP_SHELL__?.setShellSkin?.('macos'))
  await expect.poll(async () => page.evaluate(() => document.documentElement.dataset.desktopSkin)).toBe('macos')
})


test('app kit contract is importable and desktop hotkeys are off by default', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()

  const policy = await page.evaluate(async () => {
    const mod = await import('/src/desktop/app-kit/index.ts')
    const cfg = await import('/src/desktop/config/desktop-preferences.ts')
    return {
      kitId: mod.MAC_APP_KIT_ID,
      hasShell: typeof mod.MacAppShell === 'object' || typeof mod.MacAppShell === 'function',
      hotkeys: cfg.desktopConfig.enableDesktopHotkeys,
      frameLayout: mod.toWindowFrameLayout('finder'),
    }
  })
  expect(policy.kitId).toBe('mac-app-v1')
  expect(policy.hasShell).toBe(true)
  expect(policy.hotkeys).toBe(false)
  expect(policy.frameLayout).toBe('file-manager')

  // Default hotkeys must not open Spotlight on Ctrl+Space
  await page.keyboard.press('Control+Space')
  await expect(page.getByRole('dialog', { name: 'Spotlight' })).toHaveCount(0)
})


test('files finder app mounts MacAppShell contract', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '文件' })).toBeVisible()
  const opened = await page.evaluate(() => window.__HSWZ_WINDOW_MANAGER__?.openWindow('files') || window.__HSWZ_WINDOW_MANAGER__?.openWindow('desktop'))
  expect(opened).toBeTruthy()
  const finder = page.locator('.desktop-file-manager[data-mac-app-kit="mac-app-v1"]')
  await expect(finder).toBeVisible({ timeout: 15000 })
  await expect(finder).toHaveAttribute('data-mac-app-layout', 'finder')
  await expect(finder.locator('.mac-app-kit[data-mac-app-layout="finder"]')).toBeVisible()
  await expect(finder.locator('.fm-navigation-bar')).toBeVisible()
  await expect(finder.locator('.fm-view-switch')).toBeVisible()
  await expect(finder.locator('.fm-search-pill')).toBeVisible()
  await expect(finder.locator('.fm-nav-pane')).toBeVisible()
  await expect(finder.locator('.fm-nav-section-label').filter({ hasText: '个人收藏' })).toBeVisible()
  await expect(finder.locator('.fm-nav-section-label').filter({ hasText: '位置' })).toBeVisible()
  await expect(finder.locator('.fm-nav-section-label').filter({ hasText: '标签' })).toBeVisible()
  await expect(finder.locator('.fm-path-bar')).toBeVisible()
  await expect(finder.locator('.fm-status-bar')).toBeVisible()
  await expect(finder.locator('.fm-icon-size')).toBeVisible()
  await expect(finder.locator('.app-window-frame--file-manager')).toBeVisible()
  await expect(finder.locator('.fm-nav-label', { hasText: '文稿' })).toBeVisible()
  await expect(finder.locator('.fm-nav-label', { hasText: '下载' })).toBeVisible()
  await finder.locator('.fm-view-btn[aria-label="分栏"]').click()
  await expect(finder.locator('.fm-content-column')).toBeVisible()
  await expect(finder.locator('.fm-column-pane')).toBeVisible()
})

test('document viewer shell uses mac-app-v1 chrome instead of legacy teal shell', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '文本' })).toBeVisible()

  const opened = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    if (!manager) return null
    return manager.openWindow('text', {
      fileId: 1,
      fileName: 'readme.txt',
      format: 'txt',
    })
  })
  expect(opened).toBeTruthy()

  const app = page.locator('.text-editor-app[data-mac-app-kit="mac-app-v1"]')
  await expect(app).toBeVisible({ timeout: 15000 })
  const shell = page.locator('.viewer-shell[data-mac-app-kit="mac-app-v1"]')
  await expect(shell).toBeVisible({ timeout: 15000 })
  await expect(shell).toHaveAttribute('data-mac-app-layout', 'document')
  await expect(shell.locator('.vs-toolbar')).toBeVisible()
  await expect(shell.locator('.vs-app-badge')).toBeVisible()
  // legacy teal badge background should no longer exist
  const badgeBg = await shell.locator('.vs-app-badge').evaluate((el) => getComputedStyle(el).backgroundColor)
  expect(badgeBg === 'rgba(0, 0, 0, 0)' || badgeBg === 'transparent').toBeTruthy()
})

test('slice4 main products mount MacAppShell layouts', async ({ page }) => {
  const cases = [
    { appKey: 'office', root: '.office-app[data-mac-app-kit="mac-app-v1"]', layout: 'document', kitLayout: '.mac-app-kit[data-mac-app-layout="document"]' },
    { appKey: 'knowledge', root: '.kb-app[data-mac-app-kit="mac-app-v1"]', layout: 'finder', kitLayout: '.mac-app-kit[data-mac-app-layout="finder"]' },
    { appKey: 'ai', root: '.agent-app[data-mac-app-kit="mac-app-v1"]', layout: 'chat', kitLayout: '.mac-app-kit[data-mac-app-layout="chat"]' },
    { appKey: 'settings', root: '.settings-app[data-mac-app-kit="mac-app-v1"]', layout: 'settings', kitLayout: '.mac-app-kit[data-mac-app-layout="settings"]' },
  ]

  for (const item of cases) {
    await mockShell(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.desktop-shell-container')).toBeVisible()
    // Wait until product registry is mounted into Dock before opening windows.
    await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: item.appKey === 'ai' ? 'AI' : item.appKey === 'office' ? 'Office' : item.appKey === 'knowledge' ? '知识库' : '设置' })).toBeVisible()

    const opened = await page.evaluate((key) => {
      const manager = window.__HSWZ_WINDOW_MANAGER__
      if (!manager) return null
      return manager.openWindow(key)
    }, item.appKey)
    expect(opened).toBeTruthy()
    await expect(page.locator(`.desktop-window[data-window-id="${opened}"]`)).toBeVisible({ timeout: 15000 })

    const root = page.locator(item.root)
    await expect(root).toBeVisible({ timeout: 20000 })
    await expect(root).toHaveAttribute('data-mac-app-layout', item.layout)
    await expect(root.locator(item.kitLayout)).toBeVisible()
  }

  // Settings exposes desktop hotkey toggle (contract surface)
  await expect(page.locator('.settings-nav-item', { hasText: '快捷键' })).toBeVisible()
  await page.locator('.settings-nav-item', { hasText: '快捷键' }).click()
  await expect(page.getByText('启用桌面快捷键')).toBeVisible()
})


test('remaining products text/messages/media mount MacAppShell layouts', async ({ page }) => {
  // Ensure mock catalog has messages/media; text already exists in base apps.
  const ensureApp = (app) => {
    const idx = apps.findIndex(item => item.product_id === app.product_id)
    if (idx === -1) apps.push(app)
    else apps[idx] = { ...apps[idx], ...app }
  }
  ensureApp({
    product_id: 'text',
    name: '文本',
    icon: 'EditPen',
    description: '纯文本编辑',
    entry_component_key: 'text-editor/index.vue',
    default_width: 900,
    default_height: 640,
    min_width: 480,
    min_height: 320,
    category: 'text',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: true,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  })
  ensureApp({
    product_id: 'messages',
    name: '消息',
    icon: 'ChatLineRound',
    description: '即时消息',
    entry_component_key: 'im/index.vue',
    default_width: 1000,
    default_height: 720,
    min_width: 480,
    min_height: 320,
    category: 'messages',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: false,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  })
  ensureApp({
    product_id: 'media',
    name: '媒体',
    icon: 'Picture',
    description: '媒体分析',
    entry_component_key: 'media-intelligence/index.vue',
    default_width: 980,
    default_height: 700,
    min_width: 480,
    min_height: 320,
    category: 'media',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    allow_multiple: true,
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  })

  const cases = [
    { appKey: 'text', root: '.text-editor-app[data-mac-app-kit="mac-app-v1"]', layout: 'document' },
    { appKey: 'messages', root: '.im-app[data-mac-app-kit="mac-app-v1"]', layout: 'chat' },
    { appKey: 'media', root: '.media-intelligence-app[data-mac-app-kit="mac-app-v1"]', layout: 'utility' },
  ]
  for (const item of cases) {
    await mockShell(page)
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
    await expect(page.locator('.desktop-shell-container')).toBeVisible()
    // Wait for registry load via files dock button, then open target by API.
    await expect(page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '文件' })).toBeVisible()
    const opened = await page.evaluate((key) => window.__HSWZ_WINDOW_MANAGER__?.openWindow(key), item.appKey)
    expect(opened).toBeTruthy()
    const root = page.locator(item.root)
    await expect(root).toBeVisible({ timeout: 20000 })
    await expect(root).toHaveAttribute('data-mac-app-layout', item.layout)
    await expect(root.locator(`.mac-app-kit[data-mac-app-layout="${item.layout}"]`)).toBeVisible()
  }
})

test('slice5 product catalog requires mac-app-v1 uiContract and loader validates it', async ({ page }) => {
  await mockShell(page)
  await page.setViewportSize({ width: 1280, height: 800 })
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()

  const report = await page.evaluate(async () => {
    const products = await import('/src/shared/api/products.ts')
    const loader = await import('/src/desktop/app-registry/app-loader.ts')
    const catalog = await products.fetchDesktopProducts()
    const items = catalog.items || []
    const missing = items.filter(item => !item.uiContract || item.uiContract.kit !== 'mac-app-v1')
    const layouts = Object.fromEntries(items.map(item => [item.productId, item.uiContract?.layout || null]))
    const sample = items[0]
    const validation = sample ? loader.validateProductUiContract(sample) : { ok: false, warnings: ['no products'] }
    const invalid = loader.validateProductUiContract({
      productId: 'ghost-product',
      displayName: 'ghost',
      entryComponentKey: 'missing/index.vue',
    })
    return {
      count: items.length,
      missing: missing.map(item => item.productId),
      layouts,
      validationOk: validation.ok,
      invalidOk: invalid.ok,
      invalidWarnings: invalid.warnings.length,
    }
  })

  expect(report.count).toBeGreaterThanOrEqual(4)
  expect(report.missing).toEqual([])
  expect(report.validationOk).toBe(true)
  expect(report.invalidOk).toBe(false)
  expect(report.invalidWarnings).toBeGreaterThan(0)
  // mock catalog includes files/office/knowledge/ai/settings from slice4 fixtures
  expect(report.layouts.files).toBe('finder')
  expect(report.layouts.office).toBe('document')
  expect(report.layouts.ai).toBe('chat')
  expect(report.layouts.settings).toBe('settings')
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
    expect(menuBox?.height).toBe(28)
    expect(dockBox?.y).toBeGreaterThanOrEqual(viewport.height - 90)
    expect((dockBox?.x ?? 0) + (dockBox?.width ?? 0)).toBeLessThanOrEqual(viewport.width + 1)

    await dock.getByRole('button', { name: '打开 Launchpad' }).click()
    await expect(page.getByRole('dialog', { name: 'Launchpad' })).toBeVisible()
    await expect(page.locator('.desktop-launcher-app-item', { hasText: '文件' })).toBeVisible()
    await expect(page.locator('.desktop-launcher-app-item', { hasText: '后台工具' })).toHaveCount(0)
    await page.locator('.desktop-launcher-search-input').press('Escape')

    await page.getByRole('banner', { name: '系统菜单栏' }).getByRole('button', { name: '打开 Spotlight' }).click()
    await expect(page.getByRole('dialog', { name: 'Spotlight' })).toBeVisible()
    await page.locator('.spotlight-input').fill('后台工具')
    await expect(page.locator('.spotlight-result', { hasText: '后台工具' })).toContainText('后台能力')
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
    expect(windowBox?.y).toBeGreaterThanOrEqual(28)
    expect((windowBox?.x ?? 0) + (windowBox?.width ?? 0)).toBeLessThanOrEqual(viewport.width + 1)
    expect((windowBox?.y ?? 0) + (windowBox?.height ?? 0)).toBeLessThanOrEqual(viewport.height - 77)

    const controls = window.locator('.window-action-buttons button')
    await expect(controls).toHaveCount(3)
    await expect(controls.nth(0)).toHaveAttribute('aria-label', '关闭')
    await expect(controls.nth(1)).toHaveAttribute('aria-label', '最小化')
    await expect(controls.nth(2)).toHaveAttribute('aria-label', '缩放')

    await controls.nth(1).click()
    await expect(window).toHaveClass(/desktop-window-minimized/)
    await dock.getByRole('button', { name: '文件' }).click()
    await expect(window).toHaveClass(/desktop-window-entered/)
    await controls.nth(2).click()
    await expect(window).toHaveClass(/desktop-window-maximized/)
    await controls.nth(0).click()
    await expect(window).toHaveCount(0)
  })
}
