import { test, expect } from '@playwright/test'

const mockApps = [
  {
    app_id: 'agent',
    name: 'AI 助手',
    icon: 'ChatDotRound',
    description: 'Agent workspace',
    entry_component_key: 'agent/index.vue',
    default_width: 1080,
    default_height: 720,
    category: 'AI',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
  {
    app_id: 'knowledge',
    name: '知识库',
    icon: 'Collection',
    description: 'Knowledge workspace',
    entry_component_key: 'knowledge/index.vue',
    default_width: 1080,
    default_height: 720,
    category: 'AI',
    window_type: 'normal',
    permissions: ['viewer', 'editor', 'admin'],
    show_on_desktop: true,
    show_in_launcher: true,
    show_in_tray: false,
    show_in_sidebar: false,
    enabled: true,
  },
]

const taskDebtSummary = {
  summary: {
    pending: 1,
    running: 1,
    completed: 12,
    failed: 2,
  },
  recent_failed_count: 1,
  historical_debt_total: 3,
  classification: {
    recent_failed_count: 1,
    stale_pending_debt_count: 1,
    orphan_running_debt_count: 0,
    completed_semantic_failure_count: 0,
  },
}

async function mockDesktopShell(page) {
  await page.addInitScript(() => {
    localStorage.setItem('v2_auth_token', 'notification-center-test-token')
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
}

async function mockNotificationCenter(page) {
  let notificationRead = false
  let markReadCalled = false

  await page.route('**/api/notifications/unread-count', route => route.fulfill({
    status: 200,
    json: { success: true, data: { unread_count: notificationRead ? 0 : 1 }, error: null },
  }))
  await page.route('**/api/notifications', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        list: [{
          id: 101,
          title: '通知中心验收提醒',
          content: '请查看反馈中心',
          notification_type: '普通通知',
          is_read: notificationRead,
          published_at: '2026-07-04 12:00',
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/notifications/101/read', route => {
    markReadCalled = true
    notificationRead = true
    return route.fulfill({
      status: 200,
      json: { success: true, data: { id: 101 }, error: null },
    })
  })
  await page.route('**/api/tasks/worker/audit', route => route.fulfill({
    status: 200,
    json: { success: true, data: taskDebtSummary, error: null },
  }))
  await page.route('**/api/modules/call', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        total: 1,
        items: [{
          id: 7,
          title: 'Agent 视觉收口',
          status: 'needs_confirmation',
          progress_summary: '等待确认视觉方案',
          updated_at: '2026-07-04 12:01',
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/dashboard/stats', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        source_unavailable_documents: 1,
        stuck_documents: [{
          id: 31,
          filename: '视觉验收资料.pdf',
          source_available: false,
          source_state: 'missing',
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/governance/pending-count', route => route.fulfill({
    status: 200,
    json: { success: true, data: { pending_count: 1 }, error: null },
  }))

  return {
    wasMarkReadCalled: () => markReadCalled,
  }
}

async function gotoDesktop(page) {
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.locator('.taskbar-notifications-button')).toBeVisible()
}

test('notification center opens with grouped feedback layers', async ({ page }) => {
  await mockDesktopShell(page)
  await mockNotificationCenter(page)
  await gotoDesktop(page)

  const button = page.locator('.taskbar-notifications-button')
  await expect(button).toHaveAttribute('aria-expanded', 'false')
  await button.click()

  const panel = page.locator('.taskbar-notifications-panel')
  await expect(panel).toBeVisible()
  await expect(button).toHaveAttribute('aria-expanded', 'true')
  await expect(panel.locator('[role="dialog"][aria-labelledby="notification-panel-title"]')).toBeVisible()
  await expect(panel).toContainText('主反馈')
  await expect(panel).toContainText('任务')
  await expect(panel).toContainText('Agent')
  await expect(panel).toContainText('Knowledge')
  await expect(panel.locator('.feedback-action-group-primary')).toBeVisible()
  await expect(panel.locator('.feedback-action-group-task')).toBeVisible()
  await expect(panel.locator('.feedback-action-group-agent')).toBeVisible()
  await expect(panel.locator('.feedback-action-group-knowledge')).toBeVisible()
  await expect(panel).toContainText('后台任务')
  await expect(panel).toContainText('Agent 工作')
  await expect(panel).toContainText('通知中心验收提醒')

  await expect(panel).toHaveCSS('border-radius', '12px')
  const boxShadow = await panel.evaluate(node => getComputedStyle(node).boxShadow)
  expect(boxShadow).not.toBe('none')
})

test('notification center marks unread notifications as read', async ({ page }) => {
  await mockDesktopShell(page)
  const notificationMock = await mockNotificationCenter(page)
  await gotoDesktop(page)

  await page.locator('.taskbar-notifications-button').click()
  const panel = page.locator('.taskbar-notifications-panel')
  await expect(panel.locator('.notification-item-unread')).toBeVisible()

  await panel.locator('.notification-actions').getByRole('button', { name: '标为已读' }).click()
  await expect.poll(() => notificationMock.wasMarkReadCalled()).toBe(true)
  await expect(panel.locator('.notification-item-unread')).toHaveCount(0)
  await expect(panel).toContainText('✓ 已读')
})

test('notification center is keyboard reachable and closes with focus restored', async ({ page }) => {
  await mockDesktopShell(page)
  await mockNotificationCenter(page)
  await gotoDesktop(page)

  const button = page.locator('.taskbar-notifications-button')
  await expect(button).toHaveAttribute('aria-controls', 'taskbar-notifications-panel')
  await button.focus()
  await page.keyboard.press('Enter')

  const panel = page.locator('#taskbar-notifications-panel')
  await expect(panel).toBeVisible()
  await expect(panel).toBeFocused()

  await page.keyboard.press('Escape')
  await expect(panel).toBeHidden()
  await expect(button).toBeFocused()
})
