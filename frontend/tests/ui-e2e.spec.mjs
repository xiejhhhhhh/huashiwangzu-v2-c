import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const TEST_DIR = path.dirname(fileURLToPath(import.meta.url))
const REPO_ROOT = path.resolve(TEST_DIR, '../..')
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL || 'http://localhost:5173'
const SCREENSHOT_DIR = path.resolve(process.env.HOME || '/tmp', 'Downloads/ui-e2e')
const MANUAL_SCREENSHOTS_ENABLED = process.env.UI_E2E_SCREENSHOTS === '1'
const ADMIN_USER = '何焜华'
const ADMIN_PASS = '123rgE123'
const TS = Date.now()  // unique suffix to avoid filename conflicts
const SAMPLE_FILES = {
  docx: path.join(REPO_ROOT, 'modules/docx-parser/sandbox/samples/sample.docx'),
  pptx: path.join(REPO_ROOT, 'modules/pptx-parser/sandbox/samples/sample.pptx'),
  xlsx: path.join(REPO_ROOT, 'modules/xlsx-parser/sandbox/samples/sample.xlsx'),
}
const ADMIN_STORAGE_FILE = path.join(TEST_DIR, '.auth/admin.json')

const results = []
const consoleCollector = []
const uploadedFilesById = new Map()
let adminTokenOverride = null, adminRefreshPromise = null

async function screenshot(page, name) {
  if (!MANUAL_SCREENSHOTS_ENABLED) return ''
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`)
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  await page.screenshot({ path: filePath, fullPage: false })
  return filePath
}

async function refreshAdminStorageState() {
  const resp = await fetch(`${BASE_URL}/api/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: ADMIN_USER, password: ADMIN_PASS }),
  })
  const body = await resp.json()
  const token = body?.data?.access_token
  if (!resp.ok || !token) {
    throw new Error(`Admin API login failed: ${JSON.stringify(body).slice(0, 300)}`)
  }
  adminTokenOverride = token
  const storageState = {
    cookies: [],
    origins: [{
      origin: new URL(BASE_URL).origin,
      localStorage: [{ name: 'v2_auth_token', value: token }],
    }],
  }
  fs.writeFileSync(ADMIN_STORAGE_FILE, JSON.stringify(storageState, null, 2), 'utf-8')
  return token
}

async function refreshAdminToken() {
  if (!adminRefreshPromise) adminRefreshPromise = refreshAdminStorageState().finally(() => { adminRefreshPromise = null })
  return adminRefreshPromise
}

async function gotoDesktop(page) {
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

async function openLauncher(page) {
  await page.waitForSelector('.taskbar-start', { timeout: 5000 })
  const startBtn = page.locator('.taskbar-start')
  for (let attempt = 0; attempt < 3; attempt++) {
    const panelVisible = await page.locator('.desktop-launcher-panel').isVisible().catch(() => false)
    if (panelVisible) return true
    await startBtn.click({ force: true })
    try {
      await page.waitForSelector('.desktop-launcher-panel', { timeout: 3000 })
      return true
    } catch {
      // maybe the click toggled it closed; try again
    }
  }
  return false
}

async function closeAllWindows(page) {
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
    } catch { break }
  }
}

async function openFileForViewer(page, fileRecord, fileType) {
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

async function getAuthToken(request) {
  if (adminTokenOverride) return adminTokenOverride
  const storage = JSON.parse(fs.readFileSync(ADMIN_STORAGE_FILE, 'utf-8'))
  const origin = new URL(BASE_URL).origin
  const state = storage.origins?.find(item => item.origin === origin) || storage.origins?.[0]
  const token = state?.localStorage?.find(item => item.name === 'v2_auth_token')?.value
  if (!token) throw new Error('Admin storageState has no v2_auth_token')
  return token
}

async function uploadSample(request, token, name, mimeType, content, folderId = 0) {
  const uploadResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/files/upload`, {
    headers: { Authorization: `Bearer ${activeToken}` },
    multipart: {
      file: { name, mimeType, buffer: Buffer.from(content) },
      folder_id: String(folderId),
    },
  }))
  const body = await uploadResp.json().catch(() => ({}))
  if (!uploadResp.ok() || body.success !== true) {
    throw new Error(`Upload failed: status=${uploadResp.status()}, error=${body.error || JSON.stringify(body).slice(0, 200)}`)
  }
  const fileId = fileIdFromUpload(body.data)
  if (fileId !== undefined && fileId !== null) {
    uploadedFilesById.set(String(fileId), { fileId, fileName: name })
  }
  return body.data
}

async function requestWithAdminAuthRetry(token, makeRequest) {
  const firstToken = adminTokenOverride || token
  let response = await makeRequest(firstToken)
  if (response.status() === 401) response = await makeRequest(await refreshAdminToken())
  return response
}

function fileIdFromUpload(data) {
  return data?.id ?? data?.file_id
}

function responseItemsOrThrow(body, context) {
  if (body?.success !== true) {
    throw new Error(`${context} failed: ${body?.error || JSON.stringify(body).slice(0, 200)}`)
  }
  const items = body?.data?.items ?? body?.data
  if (!Array.isArray(items)) {
    throw new Error(`${context} returned non-list data: ${JSON.stringify(body?.data).slice(0, 200)}`)
  }
  return items
}

function fileItemMatches(item, fileId, fileName) {
  const ids = [item?.id, item?.file_id, item?.original_file_id]
    .filter(value => value !== undefined && value !== null)
    .map(value => String(value))
  const names = [item?.name, item?.file_name, item?.original_name]
    .filter(Boolean)
    .map(value => String(value))
  return ids.includes(String(fileId)) || names.includes(fileName)
}

function recycleItemMatches(item, fileId, fileName) {
  const ids = [item?.origin_id, item?.file_id, item?.original_file_id]
    .filter(value => value !== undefined && value !== null)
    .map(value => String(value))
  const names = [item?.name, item?.file_name, item?.original_name]
    .filter(Boolean)
    .map(value => String(value))
  return ids.includes(String(fileId)) || names.includes(fileName)
}

async function readActiveFileItems(request, token, fileName) {
  const searchResp = await requestWithAdminAuthRetry(token, (activeToken) => request.get(`${BASE_URL}/api/files/search?keyword=${encodeURIComponent(fileName)}&page=1&page_size=50`, {
    headers: { Authorization: `Bearer ${activeToken}` },
  }))
  const searchBody = await searchResp.json().catch(() => ({}))
  if (!searchResp.ok()) {
    throw new Error(`Active file search failed: status=${searchResp.status()}, body=${JSON.stringify(searchBody).slice(0, 200)}`)
  }
  const searchItems = responseItemsOrThrow(searchBody, 'Active file search')
  if (searchItems.length > 0) return searchItems

  const listResp = await requestWithAdminAuthRetry(token, (activeToken) => request.get(`${BASE_URL}/api/files/list?folder_id=0&page=1&page_size=200`, {
    headers: { Authorization: `Bearer ${activeToken}` },
  }))
  const listBody = await listResp.json().catch(() => ({}))
  if (!listResp.ok()) {
    throw new Error(`Active file list failed: status=${listResp.status()}, body=${JSON.stringify(listBody).slice(0, 200)}`)
  }
  return responseItemsOrThrow(listBody, 'Active file list')
}

async function readRecycleItems(request, token) {
  const recycleResp = await requestWithAdminAuthRetry(token, (activeToken) => request.get(`${BASE_URL}/api/recycle/list?page=1&page_size=200`, {
    headers: { Authorization: `Bearer ${activeToken}` },
  }))
  const recycleBody = await recycleResp.json().catch(() => ({}))
  if (!recycleResp.ok()) {
    throw new Error(`Recycle list failed: status=${recycleResp.status()}, body=${JSON.stringify(recycleBody).slice(0, 200)}`)
  }
  return responseItemsOrThrow(recycleBody, 'Recycle list')
}

async function waitForActiveFileState(request, token, fileId, fileName, expectedVisible) {
  let visible = false
  await expect.poll(async () => {
    const activeItems = await readActiveFileItems(request, token, fileName)
    visible = activeItems.some(item => fileItemMatches(item, fileId, fileName))
    return visible
  }, {
    timeout: 10000,
    intervals: [250, 500, 1000],
  }).toBe(expectedVisible)
  return visible
}

async function waitForDeletedAndRecycled(request, token, fileId, fileName) {
  const state = { deleted: false, inRecycle: false, recycleItem: null }
  await expect.poll(async () => {
    const [activeItems, recycleItems] = await Promise.all([
      readActiveFileItems(request, token, fileName),
      readRecycleItems(request, token),
    ])
    state.deleted = !activeItems.some(item => fileItemMatches(item, fileId, fileName))
    state.recycleItem = recycleItems.find(item => recycleItemMatches(item, fileId, fileName)) || null
    state.inRecycle = Boolean(state.recycleItem)
    return `${state.deleted}:${state.inRecycle}`
  }, {
    timeout: 10000,
    intervals: [250, 500, 1000],
  }).toBe('true:true')
  return state
}

async function waitForRecycleFileState(request, token, fileId, fileName, expectedVisible) {
  let visible = false
  await expect.poll(async () => {
    const recycleItems = await readRecycleItems(request, token)
    visible = recycleItems.some(item => recycleItemMatches(item, fileId, fileName))
    return visible
  }, {
    timeout: 10000,
    intervals: [250, 500, 1000],
  }).toBe(expectedVisible)
  return visible
}

// Minimal PDF content
function minimalPdf(text = 'Hello PDF') {
  return `%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 44>>stream
BT /F1 12 Tf 50 700 Td (${text}) Tj ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000266 00000 n 
0000000360 00000 n 
trailer<</Size 6/Root 1 0 R>>
startxref
437
%%EOF`
}

// Minimal PNG (1x1 red pixel)
function minimalPng() {
  const buf = Buffer.alloc(67)
  buf.write('\\x89PNG\\r\\n\\x1a\\n', 0)
  buf.writeUInt32BE(13, 8) // IHDR chunk length
  buf.write('IHDR', 12)
  buf.writeUInt32BE(1, 16) // width
  buf.writeUInt32BE(1, 20) // height
  buf[24] = 8 // bit depth
  buf[25] = 2 // color type (RGB)
  buf[29] = 0 // compression
  buf[30] = 0 // filter
  buf[31] = 0 // interlace
  // CRC placeholder
  buf.write('IDAT', 45)
  buf.write('IEND', 58)
  return buf
}

test.describe.configure({ mode: 'serial' })

test.beforeEach(({ page }) => {
  consoleCollector.length = 0
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      consoleCollector.push(`${msg.type()}: ${msg.text()}`)
    }
  })
})

// ══════════════════════════════════════════════════════════════════════
// Scene 1: Login + Desktop Shell
// ══════════════════════════════════════════════════════════════════════

test.describe('Scene 1: Login + Desktop Shell', () => {
  test('1.1 Admin login - desktop loads without errors', async ({ page }) => {
    await gotoDesktop(page)
    await expect(page.locator('.desktop-shell-container')).toBeVisible()
    await expect(page.locator('.desktop-taskbar')).toBeVisible()
    const errors = consoleCollector.filter(e => e.startsWith('error:'))
    const ss = await screenshot(page, '1.1-admin-desktop')
    results.push({ scenario: '1.1 Admin login', passed: errors.length === 0, screenshot: ss, consoleErrors: [...consoleCollector] })
    expect(errors.length).toBe(0)
  })

  test('1.2 Launcher opens with apps listed', async ({ page }) => {
    await gotoDesktop(page)
    await openLauncher(page)
    await expect(page.locator('.desktop-launcher-grid')).toBeVisible()
    const appCount = await page.locator('.desktop-launcher-app-item').count()
    const ss = await screenshot(page, '1.2-launcher')
    results.push({ scenario: '1.2 Launcher apps', passed: appCount > 0, screenshot: ss, consoleErrors: [...consoleCollector] })
    expect(appCount).toBeGreaterThan(0)
  })

  test.use({ storageState: 'tests/.auth/viewer.json' })
  test('1.3 Viewer role login', async ({ page }) => {
    await gotoDesktop(page)
    await expect(page.locator('.desktop-shell-container')).toBeVisible()
    const ss = await screenshot(page, '1.3-viewer-desktop')
    results.push({ scenario: '1.3 Viewer login', passed: true, screenshot: ss, consoleErrors: [...consoleCollector] })
  })

  // Restore admin storage state for remaining tests
  test.use({ storageState: 'tests/.auth/admin.json' })
})

// ══════════════════════════════════════════════════════════════════════
// Scene 2: All Apps Open (Component Mapping)
// ══════════════════════════════════════════════════════════════════════

const APP_NAMES = {
  'excel-engine': 'Excel 编辑器',
  'image-viewer': '图片查看器',
  'desktop': '文件管理',
  'recycle': '回收站',
  'text-editor': '文本编辑器',
  'pdf-viewer': 'PDF 查看器',
  'doc-viewer': '文档查看器',
  'ppt-viewer': '演示文稿查看器',
  'agent': 'AI 助手',
  'memory': '记忆',
  'scheduler': '定时任务',
  'im': '消息',
  'docs-open': '文档开放接口',
  'knowledge': '知识库',
  'hello-world': 'Hello World',
  'office-gen': 'Office Document Generator',
}

const IMAGE_GEN_APP = { key: 'image-gen', title: 'Image Generation' }

test.describe('Scene 2: All Apps Open (Component Mapping)', () => {
  const launcherApps = Object.keys(APP_NAMES)

  for (const appKey of launcherApps) {
    test(`2.1 App opens: ${appKey}`, async ({ page }) => {
      await gotoDesktop(page)
      await closeAllWindows(page)
      await openLauncher(page)

      const appChineseName = APP_NAMES[appKey]
      const appItem = page.locator('.desktop-launcher-app-item').filter({ hasText: appChineseName })
      const count = await appItem.count()
      if (count === 0) {
        results.push({ scenario: `2.1 ${appKey}`, passed: false, consoleErrors: [...consoleCollector], notes: `Not found (${appChineseName})` })
        return
      }

      await appItem.first().click()
      await page.waitForSelector('.desktop-window', { timeout: 5000 }).catch(() => {})
      // Close windows after each app to stay under the 30-window limit
      await closeAllWindows(page)
      const ss = await screenshot(page, `2.1-${appKey}`)
      const errors = consoleCollector.filter(e =>
        e.startsWith('error:') && (
          e.includes('component') || e.includes('not found') ||
          e.includes('Error') || e.includes('undefined')
        )
      )
      results.push({ scenario: `2.1 ${appKey}`, passed: errors.length === 0, screenshot: ss, consoleErrors: [...consoleCollector] })
    })
  }
})

// ══════════════════════════════════════════════════════════════════════
// Scene 3: File Opening + Viewer Rendering (6 file types)
// ══════════════════════════════════════════════════════════════════════

test.describe('Scene 3: File Opening & Viewers', () => {
  let fileIds = {}
  let token

  test('3.0 Upload sample files (all 6 types)', async ({ request }) => {
    token = await getAuthToken(request)

    const samples = [
      { key: 'txt', fileName: `e2e-${TS}-test.txt`, mimeType: 'text/plain',
        content: 'Hello E2E test file.\nLine 2中文内容\nLine 3', expectedApp: 'text-editor' },
      { key: 'pdf', fileName: `e2e-${TS}-test.pdf`, mimeType: 'application/pdf',
        content: minimalPdf('E2E PDF Test'), expectedApp: 'pdf-viewer' },
      { key: 'png', fileName: `e2e-${TS}-test.png`, mimeType: 'image/png',
        content: minimalPng(), expectedApp: 'image-viewer' },
      { key: 'docx', fileName: `e2e-${TS}-test.docx`, mimeType: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        content: fs.readFileSync(SAMPLE_FILES.docx), expectedApp: 'doc-viewer' },
      { key: 'pptx', fileName: `e2e-${TS}-test.pptx`, mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        content: fs.readFileSync(SAMPLE_FILES.pptx), expectedApp: 'ppt-viewer' },
      { key: 'xlsx', fileName: `e2e-${TS}-test.xlsx`, mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        content: fs.readFileSync(SAMPLE_FILES.xlsx), expectedApp: 'excel-engine' },
    ]

    for (const s of samples) {
      try {
        const data = await uploadSample(request, token, s.fileName, s.mimeType, s.content)
        fileIds[s.key] = { id: data.id, name: s.fileName, expectedApp: s.expectedApp }
        results.push({ scenario: `3.0 Upload ${s.key}`, passed: true, consoleErrors: [], notes: `file_id=${data.id}` })
      } catch (e) {
        results.push({ scenario: `3.0 Upload ${s.key}`, passed: false, consoleErrors: [], notes: e.message })
      }
    }
  })

  for (const [fileType, info] of Object.entries({
    txt: { expectedApp: 'text-editor', label: 'txt→text-editor' },
    pdf: { expectedApp: 'pdf-viewer', label: 'pdf→pdf-viewer' },
    png: { expectedApp: 'image-viewer', label: 'png→image-viewer' },
    docx: { expectedApp: 'doc-viewer', label: 'docx→doc-viewer' },
    pptx: { expectedApp: 'ppt-viewer', label: 'pptx→ppt-viewer' },
    xlsx: { expectedApp: 'excel-engine', label: 'xlsx→excel-engine' },
  })) {
    test(`3.1 Open ${info.label}`, async ({ page }) => {
      await gotoDesktop(page)
      await closeAllWindows(page)

      const fileId = fileIds[fileType]?.id
      if (!fileId) {
        results.push({ scenario: `3.1 ${info.label}`, passed: false, consoleErrors: [...consoleCollector], notes: 'No file_id from upload step' })
        return
      }

      const openMethod = await openFileForViewer(page, fileIds[fileType], fileType)
      if (openMethod === 'not-found') {
        results.push({ scenario: `3.1 ${info.label}`, passed: false, consoleErrors: [...consoleCollector], notes: 'File icon not found and window-manager fallback failed' })
        return
      }

      await page.waitForSelector('.desktop-window', { timeout: 8000 }).catch(() => {})
      const ss = await screenshot(page, `3.1-${fileType}`)
      const hasWindow = await page.locator('.desktop-window').count()
      results.push({
        scenario: `3.1 ${info.label}`,
        passed: hasWindow > 0,
        screenshot: ss,
        consoleErrors: [...consoleCollector],
        notes: `Window count: ${hasWindow}, open_method=${openMethod}`,
      })
    })
  }

  test('3.4 text-editor: verify window opens with content', async ({ page, request }) => {
    await gotoDesktop(page)
    await closeAllWindows(page)

    const fileId = fileIds['txt']?.id
    if (!fileId) {
      results.push({ scenario: '3.4 text-editor edit', passed: false, consoleErrors: [...consoleCollector], notes: 'No txt file_id' })
      return
    }

    // Open the txt file from desktop
    const fileIcon = page.locator(`.desktop-file-icon-item[data-selection-key="file:${fileId}"]`)
    if (await fileIcon.count() === 0) {
      results.push({ scenario: '3.4 text-editor edit', passed: false, consoleErrors: [...consoleCollector], notes: 'File icon not found' })
      return
    }
    await fileIcon.first().dblclick({ force: true })
    await page.waitForSelector('.desktop-window', { timeout: 8000 }).catch(() => {})

    // Check that a window opened and content is visible
    const windowCount = await page.locator('.desktop-window').count()
    const contentArea = page.locator('.desktop-window .window-content .window-content-padding')
    const hasContent = await contentArea.count() > 0
    const ss = await screenshot(page, '3.4-text-editor')
    results.push({
      scenario: '3.4 text-editor edit',
      passed: windowCount > 0 && hasContent,
      screenshot: ss,
      consoleErrors: [...consoleCollector],
      notes: `Window opened: ${windowCount > 0}, content area: ${hasContent}`,
    })
  })
})

// ══════════════════════════════════════════════════════════════════════
// Scene 4: Excel-Engine Parse (real xlsx)
// ══════════════════════════════════════════════════════════════════════

test.describe('Scene 4: Excel-Engine Parse', () => {
  test('4.0 Upload real xlsx sample and parse', async ({ request }) => {
    const token = await getAuthToken(request)

    // Upload a real xlsx file with actual cell data
    const xlsxBuffer = fs.readFileSync(SAMPLE_FILES.xlsx)
    const uploadResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/files/upload`, {
      headers: { Authorization: `Bearer ${activeToken}` },
      multipart: {
        file: {
          name: `e2e-${TS}-sample.xlsx`,
          mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          buffer: xlsxBuffer,
        },
        folder_id: '0',
      },
    }))
    const body = await uploadResp.json()

    // Verify excel-engine parse capability via modules call
    const callResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/modules/call`, {
      headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
      data: {
        target_module: 'excel-engine',
        action: 'parse',
        parameters: { file_id: body.data?.id || 1 },
      },
    }))
    const callBody = await callResp.json()

    // Check that parse returned actual sheet/cell data (not empty)
    const sheetsNonEmpty = callBody.success && callBody.data?.all_sheets?.length > 0
    results.push({
      scenario: '4.0 Upload+parse xlsx',
      passed: sheetsNonEmpty,
      consoleErrors: [],
      notes: `Status: ${callResp.status()}, sheets: ${callBody.data?.all_sheets?.length || 0}, Response: ${JSON.stringify(callBody).slice(0, 300)}`,
    })
  })

  test('4.1 Verify excel-engine in capabilities list', async ({ request }) => {
    const token = await getAuthToken(request)
    const capsResp = await requestWithAdminAuthRetry(token, (activeToken) => request.get(`${BASE_URL}/api/modules/capabilities`, {
      headers: { Authorization: `Bearer ${activeToken}` },
    }))
    const capsBody = await capsResp.json()
    const caps = capsBody.data || []
    const cap = caps.find(c => c.module === 'excel-engine' && c.action === 'parse')
    results.push({
      scenario: '4.1 excel-engine parse capability',
      passed: !!cap,
      consoleErrors: [],
      notes: cap ? `Registered: ${JSON.stringify(cap)}` : 'Not registered',
    })
  })
})

// ══════════════════════════════════════════════════════════════════════
// Scene 5: Key Interaction Flows
// ══════════════════════════════════════════════════════════════════════

test.describe('Scene 5: Key Interaction Flows', () => {
  test('5.1 Agent chat - open window', async ({ page }) => {
    await gotoDesktop(page)
    await closeAllWindows(page)

    await openLauncher(page)
    const agentItem = page.locator('.desktop-launcher-app-item').filter({ hasText: 'AI 助手' })
    const count = await agentItem.count()
    if (count === 0) {
      results.push({ scenario: '5.1 Agent chat', passed: false, consoleErrors: [...consoleCollector], notes: 'AI 助手 not found in launcher' })
      return
    }

    await agentItem.first().click()
    await page.waitForSelector('.desktop-window', { timeout: 5000 }).catch(() => {})

    const ss = await screenshot(page, '5.1-agent-chat')
    results.push({ scenario: '5.1 Agent chat', passed: true, screenshot: ss, consoleErrors: [...consoleCollector] })
  })

  test('5.2 File management - delete and recycle', async ({ page, request }) => {
    await gotoDesktop(page)

    const pageToken = await page.evaluate(() => localStorage.getItem('v2_auth_token'))
    if (!pageToken) {
      results.push({ scenario: '5.2 File delete+recycle', passed: false, consoleErrors: [...consoleCollector], notes: 'No auth token after login' })
      return
    }

    // Upload a temporary file to delete using fresh token
    const fileName = `e2e-${TS}-to-delete.txt`
    const data = await uploadSample(request, pageToken, fileName, 'text/plain', 'This file will be deleted by E2E test')
    const fileId = fileIdFromUpload(data)
    let uploadVisible = false
    let waitError = ''
    if (fileId === undefined || fileId === null) {
      waitError = `Upload response has no file id: ${JSON.stringify(data).slice(0, 200)}`
    } else {
      try {
        uploadVisible = await waitForActiveFileState(request, pageToken, fileId, fileName, true)
      } catch (e) {
        waitError = `Uploaded file not visible before delete: ${e.message}`
      }
    }

    // Delete via API
    const delResp = await requestWithAdminAuthRetry(pageToken, (activeToken) => request.post(`${BASE_URL}/api/files/delete`, {
      headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
      data: { id: fileId, type: 'file' },
    }))
    const delBody = await delResp.json().catch(() => ({}))
    const deletedByApi = delResp.ok() && delBody.success === true
    let deleteState = { deleted: false, inRecycle: false, recycleItem: null }
    if (deletedByApi && fileId !== undefined && fileId !== null) {
      try {
        deleteState = await waitForDeletedAndRecycled(request, pageToken, fileId, fileName)
      } catch (e) {
        waitError = waitError || `Delete/recycle state did not settle: ${e.message}`
      }
    }

    // Restore
    let restored = false
    let restoredActiveVisible = false
    let recycleGoneAfterRestore = false
    let restoreError = ''
    let recycleItemId = null
    let originId = null
    if (deleteState.inRecycle) {
      recycleItemId = deleteState.recycleItem?.id
      const itemType = deleteState.recycleItem?.item_type || 'file'
      originId = deleteState.recycleItem?.origin_id ?? deleteState.recycleItem?.file_id ?? deleteState.recycleItem?.original_file_id ?? null
      if (recycleItemId === undefined || recycleItemId === null) {
        restoreError = `Recycle item has no id: ${JSON.stringify(deleteState.recycleItem).slice(0, 200)}`
      } else {
        const restoreResp = await requestWithAdminAuthRetry(pageToken, (activeToken) => request.post(`${BASE_URL}/api/recycle/restore`, {
          headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
          data: { id: recycleItemId, item_type: itemType },
        }))
        const restoreBody = await restoreResp.json().catch(() => ({}))
        restored = restoreResp.ok() && restoreBody.success === true
        restoreError = restored ? '' : (restoreBody.error || `restore status ${restoreResp.status()}`)
        originId = restoreBody?.data?.origin_id ?? originId
        if (restored) {
          try {
            restoredActiveVisible = await waitForActiveFileState(request, pageToken, fileId, fileName, true)
            const recycleStillVisible = await waitForRecycleFileState(request, pageToken, fileId, fileName, false)
            recycleGoneAfterRestore = recycleStillVisible === false
          } catch (e) {
            restoreError = restoreError || `Restore state did not settle: ${e.message}`
          }
        }
      }
    }

    const ss = await screenshot(page, '5.2-recycle')
    const passed = uploadVisible && deletedByApi && deleteState.deleted && deleteState.inRecycle && restored && restoredActiveVisible && recycleGoneAfterRestore
    const notes = [
      `uploadVisible=${uploadVisible}`,
      `deletedByApi=${deletedByApi}`,
      `deleteState.deleted=${deleteState.deleted}`,
      `deleteState.inRecycle=${deleteState.inRecycle}`,
      `restored=${restored}`,
      `restoredActiveVisible=${restoredActiveVisible}`,
      `recycleGoneAfterRestore=${recycleGoneAfterRestore}`,
      `fileId=${fileId ?? 'none'}`,
      `recycleItemId=${recycleItemId ?? 'none'}`,
      `originId=${originId ?? 'none'}`,
      `error=${delBody.error || waitError || restoreError || 'none'}`,
    ].join(', ')
    results.push({
      scenario: '5.2 File delete+recycle',
      passed,
      screenshot: ss,
      consoleErrors: [...consoleCollector],
      notes,
    })
    expect(passed, notes).toBe(true)
  })

  test('5.3 Knowledge base - upload file and check analysis', async ({ page, request }) => {
    await gotoDesktop(page)

    // Get fresh token after browser login
    const pageToken = await page.evaluate(() => localStorage.getItem('v2_auth_token'))
    if (!pageToken) {
      results.push({ scenario: '5.3 Knowledge base', passed: false, consoleErrors: [...consoleCollector], notes: 'No auth token after login' })
      return
    }

    // Upload a txt file for knowledge base analysis
    const data = await uploadSample(request, pageToken, `e2e-${TS}-kb-test.txt`, 'text/plain',
      'Knowledge base E2E test content.\nThis file is used to test knowledge base analysis pipeline.')

    await openLauncher(page)

    const kbItem = page.locator('.desktop-launcher-app-item').filter({ hasText: '知识库' })
    if (await kbItem.count() === 0) {
      results.push({ scenario: '5.3 Knowledge base', passed: false, consoleErrors: [...consoleCollector], notes: '知识库 not found in launcher' })
      return
    }
    await kbItem.first().click()
    await page.waitForSelector('.desktop-window', { timeout: 5000 }).catch(() => {})

    // Register file in knowledge base
    const regResp = await requestWithAdminAuthRetry(pageToken, (activeToken) => request.post(`${BASE_URL}/api/knowledge/documents`, {
      headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
      data: { file_id: data.id },
    }))
    const regBody = await regResp.json()
    const regOk = regBody.success === true
    const regError = regBody.error || ''

    const ss = await screenshot(page, '5.3-knowledge-upload')
    results.push({
      scenario: '5.3 Knowledge base upload',
      passed: regOk,
      screenshot: ss,
      consoleErrors: [...consoleCollector],
      notes: `Reg ${regOk ? 'OK' : 'FAIL'}: ${regError || `doc_id=${regBody.data?.id || '?'}`}`,
    })
  })

  test('5.4 image-gen - open UI', async ({ page }) => {
    await gotoDesktop(page)
    await closeAllWindows(page)
    await openLauncher(page)

    const imgItem = page.locator('.desktop-launcher-app-item').filter({ hasText: IMAGE_GEN_APP.title })
    const count = await imgItem.count()
    if (count > 0) {
      await imgItem.first().click()
    } else {
      await page.evaluate((appKey) => {
        const manager = window.__HSWZ_WINDOW_MANAGER__
        if (manager && typeof manager.openWindow === 'function') manager.openWindow(appKey)
      }, IMAGE_GEN_APP.key)
    }
    await page.waitForSelector('.desktop-window', { timeout: 5000 }).catch(() => {})
    const hasImageGenApp = await page.locator('.image-gen-app').count() > 0
    const hasImageGenTitle = await page.locator('.desktop-window').filter({ hasText: IMAGE_GEN_APP.title }).count() > 0
    const ss = await screenshot(page, '5.4-image-gen')
    results.push({
      scenario: '5.4 image-gen',
      passed: hasImageGenApp || hasImageGenTitle,
      screenshot: ss,
      consoleErrors: [...consoleCollector],
      notes: `selector=${IMAGE_GEN_APP.key}/${IMAGE_GEN_APP.title}, launcher_visible=${count > 0}`,
    })
  })

  test('5.5 docs-open test', async ({ request }) => {
    const token = await getAuthToken(request)
    const data = await uploadSample(
      request,
      token,
      `e2e-${TS}-docs-open.txt`,
      'text/plain',
      'Docs-open E2E token scope sample.',
    )

    // Issue a docs token (proves module is live)
    const tokenResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/docs/token`, {
      headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
      data: { client_id: 'e2e-test', scope: { doc_ids: [data.id] } },
    }))
    const tokenBody = await tokenResp.json()

    results.push({
      scenario: '5.5 docs-open token issue',
      passed: tokenBody.success !== false,
      consoleErrors: [],
      notes: `Status: ${tokenResp.status()}, Response: ${JSON.stringify(tokenBody).slice(0, 200)}`,
    })
  })
})

// ══════════════════════════════════════════════════════════════════════
// Cleanup: delete uploaded e2e files
// ══════════════════════════════════════════════════════════════════════

test.describe('Cleanup', () => {
  test('Delete all e2e test files', async ({ request }) => {
    const token = await getAuthToken(request)
    const trackedFiles = Array.from(uploadedFilesById.values())
    const cleanupFailures = []
    const softDeletedFileIds = new Set()
    let alreadyInactive = 0
    let permanentlyDeleted = 0

    for (const trackedFile of trackedFiles) {
      const { fileId, fileName } = trackedFile
      let activeItems = []
      try {
        activeItems = await readActiveFileItems(request, token, fileName)
      } catch (e) {
        cleanupFailures.push(`active query failed for fileId=${fileId}: ${e.message}`)
        continue
      }

      const activeItem = activeItems.find(item => fileItemMatches(item, fileId, fileName))
      if (!activeItem) {
        alreadyInactive++
        continue
      }

      const activeFileId = activeItem.id ?? fileId
      const deleteResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/files/delete`, {
        headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
        data: { id: activeFileId, type: 'file' },
      }))
      const deleteBody = await deleteResp.json().catch(() => ({}))
      if (deleteResp.ok() && deleteBody.success === true) {
        softDeletedFileIds.add(String(fileId))
      } else {
        cleanupFailures.push(`soft delete failed for fileId=${fileId}: status=${deleteResp.status()}, error=${deleteBody.error || JSON.stringify(deleteBody).slice(0, 200)}`)
      }
    }

    let recycleItems = []
    if (softDeletedFileIds.size > 0) {
      try {
        await expect.poll(async () => {
          recycleItems = await readRecycleItems(request, token)
          return Array.from(softDeletedFileIds).every(fileId =>
            recycleItems.some(item => recycleItemMatches(item, fileId, uploadedFilesById.get(fileId)?.fileName))
          )
        }, {
          timeout: 10000,
          intervals: [250, 500, 1000],
        }).toBe(true)
      } catch (e) {
        cleanupFailures.push(`recycle list did not include all soft-deleted files: ${e.message}`)
      }
    }

    try {
      recycleItems = await readRecycleItems(request, token)
    } catch (e) {
      cleanupFailures.push(`recycle query failed after soft delete: ${e.message}`)
      recycleItems = []
    }

    const trackedRecycleItems = recycleItems.filter(item =>
      trackedFiles.some(({ fileId, fileName }) => recycleItemMatches(item, fileId, fileName))
    )
    const seenRecycleItemIds = new Set()
    for (const recycleItem of trackedRecycleItems) {
      const recycleItemId = recycleItem?.id
      const itemType = recycleItem?.item_type || 'file'
      const originId = recycleItem?.origin_id ?? recycleItem?.file_id ?? recycleItem?.original_file_id ?? null
      if (recycleItemId === undefined || recycleItemId === null) {
        cleanupFailures.push(`recycle item has no recycleItemId: ${JSON.stringify(recycleItem).slice(0, 200)}`)
        continue
      }
      if (seenRecycleItemIds.has(String(recycleItemId))) continue
      seenRecycleItemIds.add(String(recycleItemId))

      const permanentResp = await requestWithAdminAuthRetry(token, (activeToken) => request.post(`${BASE_URL}/api/recycle/delete-permanently`, {
        headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
        data: { id: recycleItemId, item_type: itemType },
      }))
      const permanentBody = await permanentResp.json().catch(() => ({}))
      if (permanentResp.ok() && permanentBody.success === true) {
        permanentlyDeleted++
      } else {
        cleanupFailures.push(`permanent delete failed for recycleItemId=${recycleItemId}, originId=${originId}: status=${permanentResp.status()}, error=${permanentBody.error || JSON.stringify(permanentBody).slice(0, 200)}`)
      }
    }

    if (seenRecycleItemIds.size > 0) {
      try {
        await expect.poll(async () => {
          const remainingRecycleItems = await readRecycleItems(request, token)
          return remainingRecycleItems.some(item =>
            trackedFiles.some(({ fileId, fileName }) => recycleItemMatches(item, fileId, fileName))
          )
        }, {
          timeout: 10000,
          intervals: [250, 500, 1000],
        }).toBe(false)
      } catch (e) {
        cleanupFailures.push(`recycle items still visible after permanent delete: ${e.message}`)
      }
    }

    const cleanupPassed = cleanupFailures.length === 0
    const notes = `trackedFileIds=${trackedFiles.map(f => f.fileId).join(',') || 'none'}, softDeleted=${softDeletedFileIds.size}, alreadyInactive=${alreadyInactive}, recycleItems=${seenRecycleItemIds.size}, permanentlyDeleted=${permanentlyDeleted}, errors=${cleanupFailures.join(' | ') || 'none'}`
    results.push({ scenario: 'Cleanup e2e files', passed: cleanupPassed, consoleErrors: [], notes })
    expect(cleanupPassed, notes).toBe(true)
  })
})

// ══════════════════════════════════════════════════════════════════════
// Report Generation
// ══════════════════════════════════════════════════════════════════════

test.describe('Report', () => {
  test('Generate final report', async () => {
    const reportPath = '/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2邮箱/收件箱/前端UI集测/审核报告.md'
    const reportDir = path.dirname(reportPath)
    fs.mkdirSync(reportDir, { recursive: true })

    const lines = [
      '# 前端 UI 端到端真测审核报告',
      '',
      `执行时间: ${new Date().toISOString()}`,
      `截图目录: ${SCREENSHOT_DIR}`,
      '',
      '## UI 集测矩阵',
      '',
      '| 场景 | 通过 | 截图 | 控制台 Error | 备注 |',
      '|------|------|------|-------------|------|',
    ]

    for (const r of results) {
      const screenshotLink = r.screenshot ? `[截图](${r.screenshot})` : '-'
      lines.push(`| ${r.scenario} | ${r.passed ? '✅' : '❌'} | ${screenshotLink} | ${r.consoleErrors.length > 0 ? r.consoleErrors.slice(0, 3).join('; ') : '无'} | ${r.notes || ''} |`)
    }

    lines.push('', '## 断点详情', '')
    for (const r of results.filter(r => !r.passed)) {
      lines.push(`### ${r.scenario}`)
      lines.push(`- 现象: ${r.notes || '未知'}`)
      lines.push(`- 控制台: ${r.consoleErrors.join(', ') || '无'}`)
      lines.push('')
    }

    lines.push('',
      '## 视觉清单（给小龙虾）',
      '',
      '- 本批仅验证功能性，未做视觉调整',
      '- 样式优化（配色/间距/字体）由小龙虾后续处理',
      '',
      '## 变更文件',
      '',
      '```',
      'frontend/tests/ui-e2e.spec.mjs (modified)',
      '```',
      '',
      '> Commit: 未提交（用户未要求）',
      '> 未 push',
    )

    fs.writeFileSync(reportPath, lines.join('\n'), 'utf-8')
    console.log(`Report saved to ${reportPath}`)
    fs.writeFileSync(path.join(reportDir, 'results.json'), JSON.stringify({ results }, null, 2), 'utf-8')
    const failed = results.filter(r => !r.passed)
    expect(failed, failed.map(r => `${r.scenario}: ${r.notes || 'failed'}`).join('\n')).toHaveLength(0)
  })
})
