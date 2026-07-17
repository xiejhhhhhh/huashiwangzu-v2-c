import { test, expect } from '@playwright/test'

import { refreshAdminToken, requestWithAdminAuthRetry } from './ui-e2e/auth.mjs'
import { gotoDesktop as gotoDesktopShell } from './ui-e2e/desktop.mjs'
import { BASE_URL } from './ui-e2e/state.mjs'

test.setTimeout(120_000)

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
  const response = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/modules/call`, {
    headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
    data: {
      target_module: 'content',
      action,
      parameters,
    },
  }))
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
  const response = await requestWithAdminAuthRetry(token, (activeToken) => {
    const activeOptions = {
      ...options,
      headers: { ...options.headers, Authorization: `Bearer ${activeToken}` },
    }
    return request[method](`${BASE_URL}${pathname}`, activeOptions)
  })
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
  if (state.fileId && state.title) {
    const encodedTitle = encodeURIComponent(state.title)
    const documentsBody = await apiJson(request, token, 'get', `/api/knowledge/documents?keyword=${encodedTitle}&page=1&page_size=100`).catch(() => null)
    for (const doc of listItems(documentsBody)) {
      if (Number(doc?.file_id) !== Number(state.fileId)) continue
      await requestWithAdminAuthRetry(token, (activeToken) => request.delete(`${BASE_URL}/api/knowledge/documents/${doc.id}`, {
        headers: { Authorization: `Bearer ${activeToken}` },
      })).catch(() => {})
    }
  }

  if (state.artifactId) {
    await requestWithAdminAuthRetry(token, (activeToken) => request.delete(`${BASE_URL}/api/artifacts/${state.artifactId}`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    })).catch(() => {})
  }
  if (state.packageId) {
    await requestWithAdminAuthRetry(token, (activeToken) => request.delete(`${BASE_URL}/api/content/packages/${state.packageId}`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    })).catch(() => {})
  }
  if (state.fileId) {
    await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/files/delete`, {
      headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
      data: { type: 'file', id: state.fileId },
    })).catch(() => {})

    const recycleResponse = await requestWithAdminAuthRetry(token, (activeToken) => request.get(`${BASE_URL}/api/recycle/list`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    })).catch(() => null)
    const recycleBody = recycleResponse ? await recycleResponse.json().catch(() => ({})) : {}
    const recycleItem = listItems(recycleBody).find(item => String(item?.origin_id) === String(state.fileId))
    if (recycleItem?.id) {
      await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/recycle/delete-permanently`, {
        headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
        data: { item_type: 'file', id: recycleItem.id },
      })).catch(() => {})
    }
  }
}

async function gotoDesktop(page) {
  await gotoDesktopShell(page)
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
  const token = await refreshAdminToken()
  const suffix = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const title = `Artifact Desktop ${suffix}`
  const state = { packageId: null, artifactId: null, fileId: null, title }

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
    await page.reload({ waitUntil: 'domcontentloaded' })
    await gotoDesktop(page)
    const icon = page.locator(`.desktop-file-icon-item[data-selection-key="file:${state.fileId}"]`)
    await expect(icon).toBeVisible({ timeout: 15000 })

    await icon.dblclick()
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
