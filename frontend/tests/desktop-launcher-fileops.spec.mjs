import { test, expect } from '@playwright/test'

const mockApps = [
  {
    app_id: 'desktop',
    name: '文件管理',
    icon: 'Folder',
    description: '管理桌面文件',
    entry_component_key: 'apps/desktop/index.vue',
    default_width: 960,
    default_height: 640,
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

async function mockDesktopShell(page) {
  await page.addInitScript(() => {
    localStorage.setItem('v2_auth_token', 'desktop-launcher-fileops-test-token')
  })
  await page.route('**/api/current-user', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: { id: 1, username: '何焜华', role: 'admin' },
      error: null,
    },
  }))
  await page.route('**/api/desktop/apps', route => route.fulfill({
    status: 200,
    json: { success: true, data: mockApps, error: null },
  }))
  await page.route('**/api/desktop/state', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: { user_id: 1, state_json: { version: 1, windows: [], appState: {}, iconPositions: {} }, version: 1 },
      error: null,
    },
  }))
  await page.route('**/api/files/list**', route => route.fulfill({
    status: 200,
    json: { success: true, data: { items: [], total: 0, page: 1, page_size: 50 }, error: null },
  }))
  await page.route('**/api/notifications/unread-count', route => route.fulfill({
    status: 200,
    json: { success: true, data: { unread_count: 0 }, error: null },
  }))
  await page.route('**/api/tasks/worker/audit', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        summary: { pending: 0, running: 0, completed: 0, failed: 0 },
        recent_failed_count: 0,
        historical_debt_total: 0,
        classification: {
          recent_failed_count: 0,
          stale_pending_debt_count: 0,
          orphan_running_debt_count: 0,
          completed_semantic_failure_count: 0,
        },
      },
      error: null,
    },
  }))
  await page.route('**/api/modules/call', route => route.fulfill({
    status: 200,
    json: { success: true, data: { total: 0, items: [] }, error: null },
  }))
  await page.route('**/api/knowledge/dashboard/stats', route => route.fulfill({
    status: 200,
    json: { success: true, data: { source_unavailable_documents: 0, stuck_documents: [] }, error: null },
  }))
  await page.route('**/api/knowledge/governance/pending-count', route => route.fulfill({
    status: 200,
    json: { success: true, data: { pending_count: 0 }, error: null },
  }))
}

async function gotoDesktop(page) {
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.locator('.taskbar-start')).toBeVisible()
}

async function openLauncher(page) {
  await page.locator('.taskbar-start').click()
  await expect(page.locator('.desktop-launcher-panel')).toBeVisible()
}

test('Launchpad excludes background capabilities and Spotlight marks them', async ({ page }) => {
  await mockDesktopShell(page)
  await gotoDesktop(page)
  await openLauncher(page)

  await expect(page.locator('.desktop-launcher-app-item', { hasText: '文件管理' })).toBeVisible()
  await expect(page.locator('.desktop-launcher-app-item', { hasText: 'Desktop Tools' })).toHaveCount(0)

  await page.locator('.desktop-launcher-search-input').press('Escape')
  await expect(page.locator('.desktop-launcher-panel')).toHaveCount(0)
  await page.getByRole('navigation', { name: 'Dock' }).getByRole('button', { name: '打开 Spotlight' }).click()
  await page.locator('.spotlight-input').fill('Desktop Tools')
  const result = page.locator('.spotlight-result', { hasText: 'Desktop Tools' })
  await expect(result).toBeVisible()
  await expect(result).toContainText('后台能力')

  await result.click()
  await expect(page.locator('.desktop-window')).toHaveCount(0)
  await expect(page.locator('.el-message')).toContainText('该能力是后台服务，不能直接打开窗口')
})

test('paste reports partial file operation failures with counts and errors', async ({ page }) => {
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await page.route('**/api/files/copy', async route => {
    const body = route.request().postDataJSON()
    if (body.id === 2) {
      await route.fulfill({
        status: 409,
        json: { success: false, data: null, error: '目标已有同名文件' },
      })
      return
    }
    await route.fulfill({
      status: 200,
      json: { success: true, data: { message: 'Copied' }, error: null },
    })
  })

  const result = await page.evaluate(async () => {
    window.__fileOpsRefreshCalled = false
    const mod = await import('/src/shared/files/use-file-operations.ts')
    const ops = mod.useFileOperations({
      refresh: () => {
        window.__fileOpsRefreshCalled = true
      },
    })
    return ops.pasteToFolder(null, [
      { id: 1, type: 'file', name: 'ok.txt' },
      { id: 2, type: 'file', name: 'bad.txt' },
    ], false)
  })

  expect(result.successCount).toBe(1)
  expect(result.failCount).toBe(1)
  expect(result.errors[0]).toMatchObject({ id: 2, name: 'bad.txt' })
  expect(result.errors[0].message).toContain('目标已有同名文件')
  await expect(page.locator('.el-message')).toContainText('部分成功：完成 1 个，失败 1 个')
  await expect(page.locator('.el-message')).not.toContainText('已粘贴')
  await expect.poll(() => page.evaluate(() => window.__fileOpsRefreshCalled)).toBe(true)
})
