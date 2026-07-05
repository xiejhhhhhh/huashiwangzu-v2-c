import { expect } from '@playwright/test'

import { BASE_URL } from './state.mjs'
import { refreshAdminStorageState } from './auth.mjs'

export async function gotoDesktop(page) {
  await page.goto(BASE_URL, { waitUntil: 'domcontentloaded' })
  for (let attempt = 0; attempt < 3; attempt++) {
    const loginVisible = await page.locator('.login-page').isVisible().catch(() => false)
    if (loginVisible) {
      const token = await refreshAdminStorageState()
      await page.evaluate((freshToken) => {
        localStorage.setItem('v2_auth_token', freshToken)
      }, token)
      await page.goto(`${BASE_URL}/desktop`, { waitUntil: 'domcontentloaded' })
    }
    try {
      await page.waitForSelector('.desktop-shell-container', { timeout: 15000 })
      await page.waitForSelector('.taskbar-start', { timeout: 5000 })
      return
    } catch {
      const returnedToLogin = await page.locator('.login-page').isVisible().catch(() => false)
      if (!returnedToLogin) await page.reload({ waitUntil: 'domcontentloaded' })
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
