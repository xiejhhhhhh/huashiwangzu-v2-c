import { test, expect } from '@playwright/test'

const mockApps = [
  {
    app_id: 'hello-world',
    name: 'Hello World',
    icon: 'Box',
    description: 'Window interaction test app',
    entry_component_key: 'hello-world/index.vue',
    default_width: 960,
    default_height: 640,
    min_width: 400,
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
]

async function mockDesktopShell(page) {
  await page.route(/^https?:\/\/[^/]+\/api\/.*/, route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/current-user') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null },
      })
    }
    if (pathname === '/api/desktop/apps') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: mockApps, error: null },
      })
    }
    if (pathname === '/api/desktop/state') {
      return route.fulfill({
        status: 200,
        json: {
          success: true,
          data: { user_id: 1, state_json: { version: 1, windows: [], appState: {}, iconPositions: {} }, version: 1 },
          error: null,
        },
      })
    }
    if (pathname.startsWith('/api/files/list')) {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { items: [], total: 0, page: 1, page_size: 50 }, error: null },
      })
    }
    if (pathname === '/api/notifications/unread-count') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { unread_count: 0 }, error: null },
      })
    }
    if (pathname === '/api/notifications') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { list: [] }, error: null },
      })
    }
    return route.fulfill({
      status: 500,
      json: { success: false, data: null, error: `Unexpected mocked API in window snap test: ${pathname}` },
    })
  })
}

async function openDesktopWindow(page) {
  await mockDesktopShell(page)
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.getByText('Hello World')).toBeVisible()

  const windowId = await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    if (!manager || typeof manager.openWindow !== 'function') return null
    return manager.openWindow('hello-world')
  })
  expect(windowId).toBeTruthy()
  await expect(page.locator('.desktop-window')).toBeVisible()

  const shellBox = await page.locator('.desktop-shell-container').boundingBox()
  const titlebarBox = await page.locator('.desktop-window .window-titlebar').boundingBox()
  if (!shellBox || !titlebarBox) throw new Error('Desktop shell or window titlebar was not measurable')
  return { shellBox, titlebarBox }
}

async function dragTitlebarTo(page, titlebarBox, x, y) {
  await page.mouse.move(titlebarBox.x + titlebarBox.width / 2, titlebarBox.y + titlebarBox.height / 2)
  await page.mouse.down()
  await page.mouse.move(x, y, { steps: 10 })
}

async function expectPreviewGeometry(page, selector, expected) {
  const previewBox = await page.locator(selector).boundingBox()
  if (!previewBox) throw new Error(`${selector} was not measurable`)
  expect(Math.abs(previewBox.x - expected.x)).toBeLessThanOrEqual(4)
  expect(Math.abs(previewBox.y - expected.y)).toBeLessThanOrEqual(4)
  expect(Math.abs(previewBox.width - expected.width)).toBeLessThanOrEqual(4)
  expect(Math.abs(previewBox.height - expected.height)).toBeLessThanOrEqual(4)
}

test('dragging a window to the left edge shows snap preview before release', async ({ page }) => {
  const { shellBox, titlebarBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x + 5, titlebarBox.y + titlebarBox.height / 2)

  await expect(page.locator('.window-snap-preview.window-snap-preview-left')).toBeVisible()
  await expectPreviewGeometry(page, '.window-snap-preview.window-snap-preview-left', {
    x: shellBox.x,
    y: shellBox.y,
    width: shellBox.width / 2,
    height: shellBox.height - 48,
  })

  await page.mouse.up()
  await expect(page.locator('.window-snap-preview')).toHaveCount(0)

  const snappedBox = await page.locator('.desktop-window').boundingBox()
  if (!snappedBox) throw new Error('Snapped window was not measurable')
  expect(Math.abs(snappedBox.width - shellBox.width / 2)).toBeLessThanOrEqual(4)
})

test('dragging a window to the right edge previews and lands on the right half', async ({ page }) => {
  const { shellBox, titlebarBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x + shellBox.width - 5, titlebarBox.y + titlebarBox.height / 2)

  await expect(page.locator('.window-snap-preview.window-snap-preview-right')).toBeVisible()
  await expectPreviewGeometry(page, '.window-snap-preview.window-snap-preview-right', {
    x: shellBox.x + shellBox.width / 2,
    y: shellBox.y,
    width: shellBox.width / 2,
    height: shellBox.height - 48,
  })

  await page.mouse.up()
  await expect(page.locator('.window-snap-preview')).toHaveCount(0)

  const snappedBox = await page.locator('.desktop-window').boundingBox()
  if (!snappedBox) throw new Error('Snapped window was not measurable')
  expect(Math.abs(snappedBox.width - shellBox.width / 2)).toBeLessThanOrEqual(4)
  expect(Math.abs(snappedBox.x - (shellBox.x + shellBox.width / 2))).toBeLessThanOrEqual(4)
})

test('dragging a window to the top edge previews maximized landing and restores original size', async ({ page }) => {
  const { shellBox, titlebarBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x + shellBox.width / 2, shellBox.y + 5)

  await expect(page.locator('.window-snap-preview.window-snap-preview-top')).toBeVisible()
  await expectPreviewGeometry(page, '.window-snap-preview.window-snap-preview-top', {
    x: shellBox.x,
    y: shellBox.y,
    width: shellBox.width,
    height: shellBox.height - 48,
  })

  await page.mouse.up()
  await expect(page.locator('.window-snap-preview')).toHaveCount(0)

  const maximizedBox = await page.locator('.desktop-window').boundingBox()
  if (!maximizedBox) throw new Error('Maximized window was not measurable')
  expect(Math.abs(maximizedBox.width - shellBox.width)).toBeLessThanOrEqual(4)
  expect(Math.abs(maximizedBox.height - (shellBox.height - 48))).toBeLessThanOrEqual(4)

  await page.locator('.desktop-window .window-titlebar').dblclick()
  await expect.poll(async () => {
    const box = await page.locator('.desktop-window').boundingBox()
    return box ? { width: Math.round(box.width), height: Math.round(box.height) } : null
  }).toEqual({ width: mockApps[0].default_width, height: mockApps[0].default_height })
  const restoredBox = await page.locator('.desktop-window').boundingBox()
  if (!restoredBox) throw new Error('Restored window was not measurable')
  expect(Math.abs(restoredBox.width - mockApps[0].default_width)).toBeLessThanOrEqual(4)
  expect(Math.abs(restoredBox.height - mockApps[0].default_height)).toBeLessThanOrEqual(4)
})
