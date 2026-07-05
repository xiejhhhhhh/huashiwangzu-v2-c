import { expect } from '@playwright/test'

import { BASE_URL } from './state.mjs'
import { ADMIN_PASS, ADMIN_USER } from './auth.mjs'

export async function gotoDesktop(page) {
  for (let attempt = 0; attempt < 4; attempt++) {
    await page.goto(`${BASE_URL}/desktop`, { waitUntil: 'domcontentloaded' })
    const loginVisible = await page.locator('.login-page').isVisible().catch(() => false)
    if (loginVisible) {
      const loginResponse = page.waitForResponse(
        response => response.url().includes('/api/login') && response.status() === 200,
        { timeout: 5000 },
      ).catch(() => null)
      await page.locator('input[placeholder="用户名"]').fill(ADMIN_USER)
      await page.locator('input[placeholder="密码"]').fill(ADMIN_PASS)
      await page.locator('button').filter({ hasText: '登录' }).click({ force: true })
      await loginResponse
      await page.goto(`${BASE_URL}/desktop`, { waitUntil: 'domcontentloaded' })
    }
    const returnedToLogin = await page.locator('.login-page').isVisible().catch(() => false)
    if (returnedToLogin) continue
    try {
      await page.waitForSelector('.desktop-shell-container', { timeout: 5000 })
      await page.waitForSelector('.taskbar-start', { timeout: 3000 })
      return
    } catch {
      if (!await page.locator('.login-page').isVisible().catch(() => false)) {
        await page.reload({ waitUntil: 'domcontentloaded' })
      }
    }
  }
  throw new Error('Desktop did not become stable after login/storageState recovery')
}

export async function openLauncher(page) {
  await gotoDesktop(page)
  const startBtn = page.locator('.taskbar-start')
  for (let attempt = 0; attempt < 3; attempt++) {
    const panelVisible = await page.locator('.desktop-launcher-panel').isVisible().catch(() => false)
    if (panelVisible) return true
    await startBtn.click({ force: true })
    try {
      await page.waitForSelector('.desktop-launcher-panel', { timeout: 3000 })
      return true
    } catch {
      // Launcher click can toggle the panel closed during transition; retry through the condition above.
    }
  }
  return false
}

export async function closeAllWindows(page) {
  await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    if (!manager || !Array.isArray(manager.windows) || typeof manager.closeWindow !== 'function') return
    for (const id of manager.windows.map(windowState => windowState.id).reverse()) {
      manager.closeWindow(id)
    }
  }).catch(() => {})
  for (let attempt = 0; attempt < 5; attempt++) {
    const closeBtns = page.locator('.window-action-close')
    const count = await closeBtns.count()
    if (count === 0) break
    try {
      await closeBtns.first().click({ timeout: 2000 })
      await expect(page.locator('.window-action-close')).toHaveCount(count - 1, { timeout: 3000 }).catch(() => {})
    } catch {
      break
    }
  }
}

export async function openFileForViewer(page, fileRecord, fileType) {
  const fileIcon = page.locator(`.desktop-file-icon-item[data-selection-key="file:${fileRecord.id}"]`)
  if (await fileIcon.count() > 0) {
    await fileIcon.first().dblclick({ force: true })
    return 'desktop-icon'
  }
  const openedByManager = await page.evaluate(({ expectedApp, id, name, format }) => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    if (!manager || typeof manager.openWindow !== 'function') return false
    return Boolean(manager.openWindow(expectedApp, {
      fileId: id,
      fileName: name,
      format,
      mode: expectedApp === 'excel-engine' || expectedApp === 'text-editor' ? 'edit' : 'view',
    }))
  }, { ...fileRecord, format: fileType })
  return openedByManager ? 'window-manager' : 'not-found'
}
