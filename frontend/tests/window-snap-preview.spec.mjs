import { test, expect } from '@playwright/test'

const mockApps = [
  {
    product_id: 'hello-world',
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

function productCatalog() {
  const app = mockApps[0]
  return {
    catalogRevision: 'test', count: 1, kind: 'products', items: [{
      productId: app.product_id,
      displayName: app.name,
      icon: app.icon,
      description: app.description,
      entryComponentKey: app.entry_component_key,
      visibility: { desktop: true, launcher: true, dock: true },
      windowPolicy: { defaultWidth: app.default_width, defaultHeight: app.default_height, minWidth: app.min_width, minHeight: app.min_height, singleton: false, allowMultiple: true },
      enabled: true, allowMultiple: true,
    }],
  }
}

async function mockDesktopShell(page) {
  await page.route(/^https?:\/\/[^/]+\/api\/.*/, route => {
    const pathname = new URL(route.request().url()).pathname
    if (pathname === '/api/current-user') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null },
      })
    }
    if (pathname === '/api/desktop/products') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: productCatalog(), error: null },
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
  const desktopWindow = page.locator('.desktop-window')
  await expect(desktopWindow).toBeVisible()
  await expect(desktopWindow).toHaveClass(/desktop-window-entered/)
  await page.waitForTimeout(250)

  const shellBox = await page.locator('.desktop-shell-container').boundingBox()
  const titlebarBox = await page.locator('.desktop-window .window-titlebar').boundingBox()
  const initialBox = await desktopWindow.boundingBox()
  if (!shellBox || !titlebarBox || !initialBox) throw new Error('Desktop shell or window was not measurable')
  return { shellBox, titlebarBox, initialBox }
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

test('dragging a window to the left edge keeps its size and clamps it inside the work area', async ({ page }) => {
  const { shellBox, titlebarBox, initialBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x - 40, titlebarBox.y + titlebarBox.height / 2)

  await expect(page.locator('.window-snap-preview')).toHaveCount(0)
  await page.mouse.up()
  const movedBox = await page.locator('.desktop-window').boundingBox()
  if (!movedBox) throw new Error('Moved window was not measurable')
  expect(Math.abs(movedBox.width - initialBox.width)).toBeLessThanOrEqual(4)
  expect(movedBox.x).toBeGreaterThanOrEqual(shellBox.x)
})

test('dragging a window to the right edge keeps its size and clamps it inside the work area', async ({ page }) => {
  const { shellBox, titlebarBox, initialBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x + shellBox.width + 40, titlebarBox.y + titlebarBox.height / 2)

  await expect(page.locator('.window-snap-preview')).toHaveCount(0)
  await page.mouse.up()
  const movedBox = await page.locator('.desktop-window').boundingBox()
  if (!movedBox) throw new Error('Moved window was not measurable')
  expect(Math.abs(movedBox.width - initialBox.width)).toBeLessThanOrEqual(4)
  expect(movedBox.x + movedBox.width).toBeLessThanOrEqual(shellBox.x + shellBox.width + 4)
})

test('dragging a window to the top edge previews maximized landing and restores original size', async ({ page }) => {
  const { shellBox, titlebarBox, initialBox } = await openDesktopWindow(page)
  await dragTitlebarTo(page, titlebarBox, shellBox.x + shellBox.width / 2, shellBox.y + 28)

  await expect(page.locator('.window-snap-preview.window-snap-preview-top')).toBeVisible()
  await expectPreviewGeometry(page, '.window-snap-preview.window-snap-preview-top', {
    x: shellBox.x,
    y: shellBox.y + 24,
    width: shellBox.width,
    height: shellBox.height - 104,
  })

  await page.mouse.up()
  await expect(page.locator('.window-snap-preview')).toHaveCount(0)

  await expect.poll(async () => {
    const box = await page.locator('.desktop-window').boundingBox()
    return box ? {
      x: Math.round(box.x),
      y: Math.round(box.y),
      width: Math.round(box.width),
      height: Math.round(box.height),
    } : null
  }).toEqual({
    x: Math.round(shellBox.x),
    y: Math.round(shellBox.y + 24),
    width: Math.round(shellBox.width),
    height: Math.round(shellBox.height - 104),
  })
  const maximizedBox = await page.locator('.desktop-window').boundingBox()
  if (!maximizedBox) throw new Error('Maximized window was not measurable')
  expect(Math.abs(maximizedBox.width - shellBox.width)).toBeLessThanOrEqual(4)
  expect(Math.abs(maximizedBox.y - (shellBox.y + 24))).toBeLessThanOrEqual(4)
  expect(Math.abs(maximizedBox.height - (shellBox.height - 104))).toBeLessThanOrEqual(4)

  await page.locator('.desktop-window .window-titlebar').dblclick()
  await expect.poll(async () => {
    const box = await page.locator('.desktop-window').boundingBox()
    return box ? { width: Math.round(box.width), height: Math.round(box.height) } : null
  }).toEqual({ width: Math.round(initialBox.width), height: Math.round(initialBox.height) })
  const restoredBox = await page.locator('.desktop-window').boundingBox()
  if (!restoredBox) throw new Error('Restored window was not measurable')
  expect(Math.abs(restoredBox.width - initialBox.width)).toBeLessThanOrEqual(4)
  expect(Math.abs(restoredBox.height - initialBox.height)).toBeLessThanOrEqual(4)
})
