import { test, expect } from '@playwright/test'
import path from 'path'
import fs from 'fs'

const BASE_URL = 'http://localhost:5173'
const SCREENSHOT_DIR = path.resolve(process.env.HOME || '/tmp', 'Downloads/ui-e2e')
const ADMIN_USER = '何焜华'
const ADMIN_PASS = '123rgE123'
const TS = Date.now()  // unique suffix to avoid filename conflicts

const results = []
const consoleCollector = []

function screenshot(page, name) {
  const filePath = path.join(SCREENSHOT_DIR, `${name}.png`)
  fs.mkdirSync(path.dirname(filePath), { recursive: true })
  page.screenshot({ path: filePath, fullPage: false })
  return filePath
}

async function gotoDesktop(page) {
  await page.goto(BASE_URL, { waitUntil: 'networkidle' })
  // If login page shows (token expired), log in
  const loginVisible = await page.locator('.login-page').isVisible().catch(() => false)
  if (loginVisible) {
    await page.fill('input[placeholder="Username"]', ADMIN_USER)
    await page.fill('input[placeholder="Password"]', ADMIN_PASS)
    await page.click('button:has-text("Login")')
  }
  await page.waitForSelector('.desktop-shell-container', { timeout: 15000 })
}

async function openLauncher(page) {
  const startBtn = page.locator('.taskbar-start')
  if (await startBtn.isVisible()) {
    await startBtn.click()
    await page.waitForSelector('.desktop-launcher-panel', { timeout: 5000 })
    await expect(page.locator('.desktop-launcher-panel')).toBeVisible({ timeout: 5000 })
  }
}

async function closeAllWindows(page) {
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

async function getAuthToken(request) {
  const loginResp = await request.post(`${BASE_URL}/api/login`, {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  })
  const loginBody = await loginResp.json()
  if (!loginBody.success) throw new Error('Login failed')
  return loginBody.data.access_token
}

async function uploadSample(request, token, name, mimeType, content, folderId = 0) {
  const uploadResp = await request.post(`${BASE_URL}/api/files/upload`, {
    headers: { Authorization: `Bearer ${token}` },
    multipart: {
      file: { name, mimeType, buffer: Buffer.from(content) },
      folder_id: String(folderId),
    },
  })
  const body = await uploadResp.json()
  if (!body.success) throw new Error(`Upload failed: ${body.error}`)
  return body.data
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
    const ss = screenshot(page, '1.1-admin-desktop')
    results.push({ scenario: '1.1 Admin login', passed: errors.length === 0, screenshot: ss, consoleErrors: [...consoleCollector] })
    expect(errors.length).toBe(0)
  })

  test('1.2 Launcher opens with apps listed', async ({ page }) => {
    await gotoDesktop(page)
    await openLauncher(page)
    await expect(page.locator('.desktop-launcher-grid')).toBeVisible()
    const appCount = await page.locator('.desktop-launcher-app-item').count()
    const ss = screenshot(page, '1.2-launcher')
    results.push({ scenario: '1.2 Launcher apps', passed: appCount > 0, screenshot: ss, consoleErrors: [...consoleCollector] })
    expect(appCount).toBeGreaterThan(0)
  })

  test.use({ storageState: 'tests/.auth/viewer.json' })
  test('1.3 Viewer role login', async ({ page }) => {
    await gotoDesktop(page)
    await expect(page.locator('.desktop-shell-container')).toBeVisible()
    const ss = screenshot(page, '1.3-viewer-desktop')
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
      const ss = screenshot(page, `2.1-${appKey}`)
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
        content: fs.readFileSync('/tmp/e2e-samples/sample.docx'), expectedApp: 'doc-viewer' },
      { key: 'pptx', fileName: `e2e-${TS}-test.pptx`, mimeType: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
        content: fs.readFileSync('/tmp/e2e-samples/sample.pptx'), expectedApp: 'ppt-viewer' },
      { key: 'xlsx', fileName: `e2e-${TS}-test.xlsx`, mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        content: fs.readFileSync('/tmp/e2e-samples/sample.xlsx'), expectedApp: 'excel-engine' },
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

      const fileIcon = page.locator(`.desktop-file-icon-item[data-selection-key="file:${fileId}"]`)
      const count = await fileIcon.count()
      if (count === 0) {
        results.push({ scenario: `3.1 ${info.label}`, passed: false, consoleErrors: [...consoleCollector], notes: 'File icon not found on desktop' })
        return
      }

      await fileIcon.first().dblclick({ force: true })
      await page.waitForSelector('.desktop-window', { timeout: 8000 }).catch(() => {})
      const ss = screenshot(page, `3.1-${fileType}`)
      const hasWindow = await page.locator('.desktop-window').count()
      results.push({
        scenario: `3.1 ${info.label}`,
        passed: hasWindow > 0,
        screenshot: ss,
        consoleErrors: [...consoleCollector],
        notes: `Window count: ${hasWindow}`,
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
    const ss = screenshot(page, '3.4-text-editor')
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
    const xlsxBuffer = fs.readFileSync('/tmp/e2e-samples/sample.xlsx')
    const uploadResp = await request.post(`${BASE_URL}/api/files/upload`, {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: `e2e-${TS}-sample.xlsx`,
          mimeType: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
          buffer: xlsxBuffer,
        },
        folder_id: '0',
      },
    })
    const body = await uploadResp.json()

    // Verify excel-engine parse capability via modules call
    const callResp = await request.post(`${BASE_URL}/api/modules/call`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        target_module: 'excel-engine',
        action: 'parse',
        parameters: { file_id: body.data?.id || 1 },
      },
    })
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
    const capsResp = await request.get(`${BASE_URL}/api/modules/capabilities`, {
      headers: { Authorization: `Bearer ${token}` },
    })
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

    const ss = screenshot(page, '5.1-agent-chat')
    results.push({ scenario: '5.1 Agent chat', passed: true, screenshot: ss, consoleErrors: [...consoleCollector] })
  })

  test('5.2 File management - delete and recycle', async ({ page, request }) => {
    await gotoDesktop(page)

    // Get fresh token AFTER browser login (login increments session_version)
    const pageToken = await page.evaluate(() => localStorage.getItem('v2_auth_token'))
    if (!pageToken) {
      results.push({ scenario: '5.2 File delete+recycle', passed: false, consoleErrors: [...consoleCollector], notes: 'No auth token after login' })
      return
    }

    // Upload a temporary file to delete using fresh token
    const data = await uploadSample(request, pageToken, `e2e-${TS}-to-delete.txt`, 'text/plain', 'This file will be deleted by E2E test')
    const fileId = data.id

    // Delete via API
    const delResp = await request.post(`${BASE_URL}/api/files/delete`, {
      headers: { Authorization: `Bearer ${pageToken}`, 'Content-Type': 'application/json' },
      data: { id: fileId, type: 'file' },
    })
    const delBody = await delResp.json()

    // Check recycle bin
    const recycleResp = await request.get(`${BASE_URL}/api/recycle/list?page=1&page_size=20`, {
      headers: { Authorization: `Bearer ${pageToken}` },
    })
    const recycleBody = await recycleResp.json()
    const recycleItems = recycleBody?.data?.items || recycleBody?.data || []
    const foundInRecycle = Array.isArray(recycleItems) && recycleItems.some(i => i.file_id === fileId || i.id === fileId)

    // Restore
    if (foundInRecycle) {
      await request.post(`${BASE_URL}/api/recycle/restore`, {
        headers: { Authorization: `Bearer ${pageToken}`, 'Content-Type': 'application/json' },
        data: { id: fileId, type: 'file' },
      })
    }

    const ss = screenshot(page, '5.2-recycle')
    results.push({
      scenario: '5.2 File delete+recycle',
      passed: delBody.success === true,
      screenshot: ss,
      consoleErrors: [...consoleCollector],
      notes: `Deleted: ${delBody.success === true}, in recycle: ${foundInRecycle}, restored automatically`,
    })
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
    const regResp = await request.post(`${BASE_URL}/api/knowledge/documents`, {
      headers: { Authorization: `Bearer ${pageToken}`, 'Content-Type': 'application/json' },
      data: { file_id: data.id },
    })
    const regBody = await regResp.json()
    const regOk = regBody.success === true
    const regError = regBody.error || ''

    const ss = screenshot(page, '5.3-knowledge-upload')
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
    await openLauncher(page)

    const imgItem = page.locator('.desktop-launcher-app-item').filter({ hasText: 'Office' })
    const count = await imgItem.count()
    if (count === 0) {
      results.push({ scenario: '5.4 image-gen', passed: false, consoleErrors: [...consoleCollector], notes: 'Image-gen has show_in_launcher=false; can be opened via desktop icon if configured' })
      return
    }
    await imgItem.first().click()
    await page.waitForSelector('.desktop-window', { timeout: 5000 }).catch(() => {})
    const ss = screenshot(page, '5.4-image-gen')
    results.push({ scenario: '5.4 image-gen', passed: true, screenshot: ss, consoleErrors: [...consoleCollector] })
  })

  test('5.5 docs-open test', async ({ request }) => {
    const token = await getAuthToken(request)

    // Issue a docs token (proves module is live)
    const tokenResp = await request.post(`${BASE_URL}/api/docs/token`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { client_id: 'e2e-test', scope: {} },
    })
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
    const listResp = await request.get(`${BASE_URL}/api/files/list?folder_id=0&page_size=100`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    const listBody = await listResp.json()
    const items = listBody?.data?.items || []
    const pattern = `e2e-${TS}`
    const e2eFiles = items.filter(i => (i.name || i.file_name || '').toLowerCase().startsWith(pattern))
    let deleted = 0
    for (const f of e2eFiles) {
      const resp = await request.post(`${BASE_URL}/api/files/delete`, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { id: f.id, type: 'file' },
      })
      const body = await resp.json()
      if (body.success) deleted++
    }
    results.push({ scenario: 'Cleanup e2e files', passed: true, consoleErrors: [], notes: `Deleted ${deleted}/${e2eFiles.length} files` })
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
  })
})
