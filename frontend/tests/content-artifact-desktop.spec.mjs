import { test, expect } from '@playwright/test'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url))
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
const ADMIN_STORAGE_FILE = path.join(TEST_DIR, '.auth/admin.json')
const ADMIN_USER = '何焜华'
const ADMIN_PASS = '123rgE123'

function readAdminToken() {
  const storage = JSON.parse(fs.readFileSync(ADMIN_STORAGE_FILE, 'utf-8'))
  const origin = new URL(BASE_URL).origin
  const state = storage.origins?.find(item => item.origin === origin) || storage.origins?.[0]
  const token = state?.localStorage?.find(item => item.name === 'v2_auth_token')?.value
  if (!token) throw new Error('Admin storageState has no v2_auth_token')
  return token
}

async function loginAdminToken(request) {
  const response = await request.post(`${BASE_URL}/api/login`, {
    headers: { 'Content-Type': 'application/json' },
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  })
  const body = await response.json().catch(() => ({}))
  const token = body?.data?.access_token
  if (!response.ok() || !token) {
    throw new Error(`Admin login failed: ${JSON.stringify(body).slice(0, 300)}`)
  }
  return token
}

function unwrapEnvelope(body, context) {
  if (body?.success !== true) {
    throw new Error(`${context} failed: ${body?.error || JSON.stringify(body).slice(0, 300)}`)
  }
  return body.data
}

function unwrapCapability(body, context) {
  const data = unwrapEnvelope(body, context)
  if (data?.success === false) {
    throw new Error(`${context} capability failed: ${data.error || JSON.stringify(data).slice(0, 300)}`)
  }
  if (data?.success === true && Object.prototype.hasOwnProperty.call(data, 'data')) return data.data
  return data
}

async function callCapability(request, token, action, parameters) {
  const response = await request.post(`${BASE_URL}/api/modules/call`, {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    data: {
      target_module: 'content',
      action,
      parameters,
    },
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok()) {
    throw new Error(`content:${action} HTTP ${response.status()}: ${JSON.stringify(body).slice(0, 300)}`)
  }
  return unwrapCapability(body, `content:${action}`)
}

async function apiJson(request, token, method, pathname, data) {
  const options = {
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
  }
  if (data !== undefined) options.data = data
  const response = await request[method](`${BASE_URL}${pathname}`, options)
  const body = await response.json().catch(() => ({}))
  if (!response.ok()) {
    throw new Error(`${method.toUpperCase()} ${pathname} HTTP ${response.status()}: ${JSON.stringify(body).slice(0, 300)}`)
  }
  return body
}

function listItems(body) {
  const items = body?.data?.items ?? body?.data ?? []
  return Array.isArray(items) ? items : []
}

async function cleanupPublishedArtifact(request, token, state) {
  if (state.artifactId) {
    await request.delete(`${BASE_URL}/api/artifacts/${state.artifactId}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {})
  }
  if (state.packageId) {
    await request.delete(`${BASE_URL}/api/content/packages/${state.packageId}`, {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => {})
  }
  if (state.fileId) {
    await request.post(`${BASE_URL}/api/files/delete`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { type: 'file', id: state.fileId },
    }).catch(() => {})

    const recycleResponse = await request.get(`${BASE_URL}/api/recycle/list`, {
      headers: { Authorization: `Bearer ${token}` },
    }).catch(() => null)
    const recycleBody = recycleResponse ? await recycleResponse.json().catch(() => ({})) : {}
    const recycleItem = listItems(recycleBody).find(item => String(item?.origin_id) === String(state.fileId))
    if (recycleItem?.id) {
      await request.post(`${BASE_URL}/api/recycle/delete-permanently`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { item_type: 'file', id: recycleItem.id },
      }).catch(() => {})
    }
  }
}

async function gotoDesktop(page) {
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.locator('.desktop-file-icon-item').first()).toBeVisible({ timeout: 15000 }).catch(() => {})
}

async function closeAllWindows(page) {
  await page.evaluate(() => {
    const manager = window.__HSWZ_WINDOW_MANAGER__
    if (!manager || !Array.isArray(manager.windows) || typeof manager.closeWindow !== 'function') return
    for (const id of manager.windows.map(windowState => windowState.id).reverse()) {
      manager.closeWindow(id)
    }
  })
  await expect(page.locator('.desktop-window')).toHaveCount(0, { timeout: 5000 }).catch(() => {})
}

test('content publish artifact is visible, openable, and downloadable from desktop file entry', async ({ page, request }) => {
  const token = await loginAdminToken(request).catch(() => readAdminToken())
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const title = `Artifact Desktop ${suffix}`
  const state = { packageId: null, artifactId: null, fileId: null }

  try {
    await page.addInitScript((freshToken) => {
      localStorage.setItem('v2_auth_token', freshToken)
    }, token)

    const writeResult = await callCapability(request, token, 'write_ir', {
      content_ir: {
        schema_version: '1.0',
        content_type: 'document',
        title,
        blocks: [
          { type: 'heading', text: title, data: { level: 1 } },
          { type: 'paragraph', text: `Published body ${suffix}` },
        ],
      },
    })
    state.packageId = writeResult.package_id
    expect(state.packageId).toBeTruthy()

    const publishResult = await callCapability(request, token, 'publish', {
      package_id: state.packageId,
    })
    state.artifactId = publishResult.artifact_id
    state.fileId = publishResult.file_id

    expect(publishResult.published).toBe(true)
    expect(publishResult.publish_status).toBe('published_artifact/file')
    expect(publishResult.desktop_visible).toBe(true)
    expect(publishResult.download_url).toBe(`/api/files/download/${state.fileId}`)
    expect(publishResult.open_url).toBe(`/api/files/preview/${state.fileId}`)
    expect(publishResult.artifact?.file_id).toBe(state.fileId)
    expect(publishResult.artifact?.desktop_visible).toBe(true)

    const artifactBody = await apiJson(request, token, 'get', `/api/artifacts/${state.artifactId}`)
    const artifact = unwrapEnvelope(artifactBody, 'get artifact')
    expect(artifact.file_id).toBe(state.fileId)

    const fileListBody = await apiJson(request, token, 'get', '/api/files/list?folder_id=0&page=1&page_size=200')
    const fileItems = listItems(fileListBody)
    expect(fileItems.some(item => Number(item?.id) === Number(state.fileId))).toBe(true)

    await gotoDesktop(page)
    await closeAllWindows(page)
    const icon = page.locator(`.desktop-file-icon-item[data-selection-key="file:${state.fileId}"]`)
    await expect(icon).toBeVisible({ timeout: 15000 })

    await icon.dblclick({ force: true })
    await expect.poll(async () => page.evaluate((fileId) => {
      const manager = window.__HSWZ_WINDOW_MANAGER__
      if (!manager || !Array.isArray(manager.windows)) return false
      return manager.windows.some(windowState => Number(windowState?.payload?.fileId) === Number(fileId))
    }, state.fileId), { timeout: 10000 }).toBe(true)
    await expect(page.locator('.desktop-window').first()).toBeVisible()

    const downloadResponse = page.waitForResponse(response => (
      response.url().includes(`/api/files/download/${state.fileId}`) && response.status() === 200
    ))
    await icon.click({ button: 'right', force: true })
    const menu = page.locator('.v40-ctx-menu')
    await expect(menu).toBeVisible()
    await menu.locator('.v40-ctx-item').filter({ hasText: '下载到本地' }).click()
    await downloadResponse
  } finally {
    await closeAllWindows(page).catch(() => {})
    await cleanupPublishedArtifact(request, token, state)
  }
})
