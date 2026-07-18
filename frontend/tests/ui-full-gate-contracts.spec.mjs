import { test, expect } from '@playwright/test'

const mockApps = [
  {
    app_id: 'knowledge',
    name: '知识库',
    icon: 'Collection',
    description: 'Knowledge workspace',
    entry_component_key: 'knowledge/index.vue',
    default_width: 1120,
    default_height: 760,
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
    app_id: 'agent',
    name: 'AI',
    icon: 'ChatDotRound',
    description: 'Agent workspace',
    entry_component_key: 'agent/index.vue',
    default_width: 1120,
    default_height: 760,
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

const knowledgeDoc = {
  id: 301,
  file_id: 501,
  filename: 'ui-full-gate-knowledge.md',
  extension: 'md',
  file_size: 1024,
  parse_status: 'done',
  vector_status: 'done',
  raw_status: 'done',
  fusion_status: 'done',
  total_chunks: 4,
  total_pages: 2,
  parse_error: null,
  source_available: true,
  source_state: 'available',
}

const knowledgeProgress = {
  document_id: 301,
  filename: 'ui-full-gate-knowledge.md',
  total_pages: 2,
  overall_status: 'done',
  overall_percent: 100,
  current_stage: 'complete',
  stages: [
    { key: 'parse', label: '解析', status: 'done', percent: 100, done: 1, total: 1 },
    { key: 'vector', label: '索引', status: 'done', percent: 100, done: 4, total: 4 },
  ],
}

const workflowSummary = {
  id: 77,
  title: 'UI Full Gate workflow',
  status: 'needs_confirmation',
  terminal_status: null,
  verification_status: 'debt',
  progress_summary: '验证 Agent workflow evidence 展示',
  needs_confirmation: true,
  artifact_summary: { report: 'playwright-summary.json' },
  updated_at: '2026-07-04T12:00:00Z',
  developer_summary: 'workflow ledger is visible',
  step_count: 2,
  tool_call_count: 1,
  failure_count: 1,
  artifact_count: 1,
  verification_count: 1,
  reference_count: 2,
  queue_task_ids: [7001],
  multi_agent_summary: {
    items: [{
      id: 'subagent-a',
      title: '子代理验证',
      status: 'completed',
      completion_summary: '检查 UI evidence',
      failure_reason: null,
      reference_ids: ['ref-42'],
      artifact_ids: [9001],
      next_action: '主会话复验',
    }],
  },
}

function failUnexpectedRoute(route, message) {
  return route.fulfill({
    status: 500,
    json: { success: false, data: null, error: message },
  })
}

function requestJson(route) {
  return route.request().postDataJSON()
}

function isApiPath(url, pathname) {
  return new URL(url).pathname === pathname
}

async function mockDesktopShell(page) {
  await page.route('**/api/current-user', route => route.fulfill({
    status: 200,
    json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null },
  }))
  await page.route('**/api/desktop/products', route => route.fulfill({
    status: 200,
    json: { success: true, data: {
      catalogRevision: 'test', count: mockApps.length, kind: 'products', items: mockApps.map(app => ({
        productId: app.app_id,
        displayName: app.name,
        icon: app.icon,
        description: app.description,
        entryComponentKey: app.entry_component_key,
        visibility: { desktop: app.show_on_desktop, launcher: app.show_in_launcher, dock: app.show_on_desktop },
        windowPolicy: { defaultWidth: app.default_width, defaultHeight: app.default_height, minWidth: app.min_width, minHeight: app.min_height, singleton: !app.allow_multiple, allowMultiple: Boolean(app.allow_multiple) },
        enabled: app.enabled,
        allowMultiple: Boolean(app.allow_multiple),
      })),
    }, error: null },
  }))
  await page.route('**/api/desktop/state', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: { user_id: 1, state_json: { version: 1, windows: [], appState: {}, iconPositions: {} }, version: 1 },
      error: null,
    },
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
  await page.route('**/api/modules/call', route => {
    const payload = requestJson(route)
    if (payload?.target_module !== 'agent' || payload?.action !== 'list_workflows') {
      return failUnexpectedRoute(route, `Unexpected module call: ${JSON.stringify(payload)}`)
    }
    return route.fulfill({
      status: 200,
      json: { success: true, data: { total: 0, items: [] }, error: null },
    })
  })
  await page.route('**/api/knowledge/dashboard/stats**', route => route.fulfill({
    status: 200,
    json: { success: true, data: { source_unavailable_documents: 0, stuck_documents: [] }, error: null },
  }))
  await page.route('**/api/knowledge/governance/pending-count', route => route.fulfill({
    status: 200,
    json: { success: true, data: { pending_count: 0 }, error: null },
  }))
}

async function mockKnowledgeApis(page) {
  await page.route('**/api/files/tree', route => route.fulfill({
    status: 200,
    json: { success: true, data: [], error: null },
  }))
  await page.route('**/api/files/list**', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 501,
          name: knowledgeDoc.filename,
          extension: 'md',
          is_folder: false,
          parent_id: null,
          created_at: '2026-07-04T12:00:00Z',
        }],
        total: 1,
        page: 1,
        page_size: 200,
      },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/documents?page=1&page_size=100', route => route.fulfill({
    status: 200,
    json: { success: true, data: { items: [knowledgeDoc], total: 1 }, error: null },
  }))
  await page.route('**/api/knowledge/documents/by-files', route => route.fulfill({
    status: 200,
    json: { success: true, data: { items: [knowledgeDoc] }, error: null },
  }))
  await page.route('**/api/knowledge/documents/progress-batch', route => {
    const payload = requestJson(route)
    if (route.request().method() !== 'POST' || !Array.isArray(payload?.document_ids) || !payload.document_ids.includes(301)) {
      return failUnexpectedRoute(route, `Unexpected progress-batch request: ${JSON.stringify(payload)}`)
    }
    return route.fulfill({
      status: 200,
      json: { success: true, data: { 301: knowledgeProgress }, error: null },
    })
  })
  await page.route('**/api/knowledge/documents/301/progress', route => route.fulfill({
    status: 200,
    json: { success: true, data: knowledgeProgress, error: null },
  }))
  await page.route('**/api/knowledge/documents/301/ingest-status', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        document_id: 301,
        file_id: 501,
        filename: knowledgeDoc.filename,
        source_available: true,
        source_state: 'available',
        stage: 'complete',
        status: 'done',
        pipeline_status: 'deep_ready',
        parse_status: 'done',
        vector_status: 'done',
        raw_status: 'done',
        fusion_status: 'done',
        stage_summary: {
          graph: { status: 'done', ready: true, count: 3, node_count: 3, chunk_entity_count: 2 },
        },
        search_ready: true,
        deep_ready: true,
        last_error: null,
        next_action: 'ready',
      },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/documents/301/fusions', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: { items: [{ page: 1, page_title: '来源说明', fused_text: 'source context body', confidence: 0.91 }] },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/documents/301/profile', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        doc_type: '验收资料',
        subject: 'UI Full Gate',
        doc_summary: '用于验证搜索来源解释字段。',
        key_entities: JSON.stringify([{ name: 'Playwright' }]),
        chapter_structure: JSON.stringify([{ title: '来源说明', page: 1 }]),
      },
      error: null,
    },
  }))
  await page.route('**/api/knowledge/documents/301/relations', route => route.fulfill({
    status: 200,
    json: { success: true, data: { relations: [] }, error: null },
  }))
  await page.route('**/api/knowledge/search', route => {
    const payload = requestJson(route)
    if (route.request().method() !== 'POST' || payload?.query !== 'source score' || payload?.top_k !== 10) {
      return failUnexpectedRoute(route, `Unexpected knowledge search request: ${JSON.stringify(payload)}`)
    }
    return route.fulfill({
      status: 200,
      json: {
        success: true,
        data: {
          results: [{
            chunk_id: 9301,
            document_id: 301,
            file_id: 501,
            source_file_id: 501,
            page: 1,
            section: '来源说明',
            paragraph: 3,
            block_type: 'paragraph',
            text: 'Knowledge search result context includes source and score fields.',
            score: 0.82,
            rrf_score: 0.74,
            document_name: knowledgeDoc.filename,
            source_file: 'source-guide.md',
            source_module: 'knowledge',
            source_type: 'file',
            retrieval_source: 'hybrid',
            content_package_id: 8801,
            block_id: 'block-source-1',
            explain: {
              retrieval_source: 'hybrid',
              score: 0.82,
              rrf_score: 0.74,
              source_file_id: 501,
              source_file: 'source-guide.md',
              page: 1,
              section: '来源说明',
              paragraph: 3,
            },
          }],
        },
        error: null,
      },
    })
  })
}

async function mockAgentApis(page) {
  await page.route('**/api/agent/profiles', route => route.fulfill({
    status: 200,
    json: { success: true, data: [{ key: 'default', name: '默认', provider: 'test', model: 'mock' }], error: null },
  }))
  await page.route('**/api/agent/tools', route => route.fulfill({
    status: 200,
    json: { success: true, data: [], error: null },
  }))
  await page.route('**/api/agent/conversations', route => route.fulfill({
    status: 200,
    json: { success: true, data: [{ id: 401, title: 'UI Full Gate 对话', status: 'active' }], error: null },
  }))
  await page.route('**/api/agent/conversations/401/messages', route => route.fulfill({
    status: 200,
    json: { success: true, data: [], error: null },
  }))
  await page.route('**/api/agent/workflows/governance-summary', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        total: 1,
        failed: 1,
        partial: 0,
        completed: 0,
        needs_confirmation: 1,
        with_artifacts: 1,
        with_references: 1,
        average_duration_ms: 1200,
        recent_errors: [],
      },
      error: null,
    },
  }))
  await page.route(
    url => isApiPath(url, '/api/agent/workflows'),
    route => {
      const url = new URL(route.request().url())
      if (url.searchParams.get('limit') !== '50') {
        return failUnexpectedRoute(route, `Unexpected workflow list query: ${url.search}`)
      }
      return route.fulfill({
        status: 200,
        json: { success: true, data: { items: [workflowSummary], total: 1 }, error: null },
      })
    },
  )
  await page.route('**/api/agent/workflows/77', route => route.fulfill({
    status: 200,
    json: { success: true, data: workflowSummary, error: null },
  }))
  await page.route('**/api/agent/workflows/77/multi-agent-summary', route => route.fulfill({
    status: 200,
    json: { success: true, data: workflowSummary.multi_agent_summary, error: null },
  }))
  await page.route('**/api/agent/workflows/77/steps', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 11,
          run_id: 77,
          step_key: 'collect_evidence',
          title: '收集证据',
          type: 'verification',
          status: 'completed',
          summary: '读取 Playwright 摘要',
          input_ref: { source: 'release_gate' },
          output_ref: { evidence_id: 'ev-step-1' },
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/agent/workflows/77/tool-calls', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 21,
          run_id: 77,
          step_id: 11,
          tool_name: 'playwright',
          target_module: 'frontend',
          action: 'test',
          caller: 'agent',
          side_effect_level: 'read',
          approval_policy: 'auto',
          status: 'completed',
          arguments_hash: 'abcdef1234567890',
          result_ref: { artifact_id: 9001, path: 'playwright-summary.json' },
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/agent/workflows/77/artifacts', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 31,
          run_id: 77,
          step_id: 11,
          artifact_type: 'playwright_report',
          storage_kind: 'file',
          storage_ref: { file_id: 9001, path: 'playwright-summary.json' },
          visibility: 'internal',
          lifecycle: 'active',
          summary: 'UI full gate report',
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/agent/workflows/77/verifications', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 41,
          run_id: 77,
          step_id: 11,
          verification_type: 'ui_gate',
          status: 'fail',
          command_or_capability: 'npm run test:browser',
          evidence_ref: { log: 'ui-failure.log' },
          summary: '发现一个历史失败',
          is_required_for_completion: true,
          duration_ms: 1200,
        }],
      },
      error: null,
    },
  }))
  await page.route('**/api/agent/workflows/77/failures', route => route.fulfill({
    status: 200,
    json: {
      success: true,
      data: {
        items: [{
          id: 51,
          run_id: 77,
          step_id: 11,
          tool_call_id: 21,
          failure_type: 'ui_assertion_failed',
          error_signature: 'locator missing evidence count',
          retryable: true,
          retry_count: 1,
          next_action: 'fix_test',
          evidence_ref: {
            ref_key: 'file_id',
            ref_id: 9901,
            source_module: 'agent',
            snippet: 'workflow-evidence.png',
          },
          handoff_note: '补齐 evidence 断言',
        }],
      },
      error: null,
    },
  }))
}

async function mockApiFallback(page) {
  await page.route('**/api/**', route => {
    const pathname = new URL(route.request().url()).pathname
    if (!pathname.startsWith('/api/')) return route.fallback()
    if (pathname === '/api/current-user') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { id: 1, username: '何焜华', role: 'admin' }, error: null },
      })
    }
    if (pathname === '/api/desktop/products') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: {
          catalogRevision: 'test', count: mockApps.length, kind: 'products', items: mockApps.map(app => ({
            productId: app.app_id,
            displayName: app.name,
            icon: app.icon,
            description: app.description,
            entryComponentKey: app.entry_component_key,
            visibility: { desktop: app.show_on_desktop, launcher: app.show_in_launcher, dock: app.show_on_desktop },
            windowPolicy: { defaultWidth: app.default_width, defaultHeight: app.default_height, minWidth: app.min_width, minHeight: app.min_height, singleton: !app.allow_multiple, allowMultiple: Boolean(app.allow_multiple) },
            enabled: app.enabled,
            allowMultiple: Boolean(app.allow_multiple),
          })),
        }, error: null },
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
    if (pathname === '/api/notifications/unread-count') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { unread_count: 0 }, error: null },
      })
    }
    if (pathname === '/api/tasks/worker/audit') {
      return route.fulfill({
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
      })
    }
    if (pathname === '/api/modules/call') {
      return route.fulfill({
        status: 200,
        json: { success: true, data: { total: 0, items: [] }, error: null },
      })
    }
    if (
      pathname.startsWith('/api/agent') ||
      pathname.startsWith('/api/knowledge') ||
      pathname.startsWith('/api/files')
    ) {
      return failUnexpectedRoute(route, `Unexpected API request: ${route.request().method()} ${pathname}`)
    }
    return failUnexpectedRoute(route, `Unexpected API request: ${route.request().method()} ${pathname}`)
  })
}

async function gotoDesktop(page) {
  await page.goto('/desktop', { waitUntil: 'domcontentloaded' })
  await expect(page.locator('.desktop-shell-container')).toBeVisible()
  await expect(page.locator('.taskbar-start')).toBeVisible()
}

async function openLauncherApp(page, appName) {
  await page.locator('.taskbar-start').click()
  await expect(page.locator('.desktop-launcher-panel')).toBeVisible()
  await page.locator('.desktop-launcher-app-item').filter({ hasText: appName }).click()
  await expect(page.locator('.desktop-window').filter({ hasText: appName }).first()).toBeVisible()
}

test('knowledge search exposes source, chunk, score, and context metadata', async ({ page }) => {
  await mockApiFallback(page)
  await mockDesktopShell(page)
  await mockKnowledgeApis(page)
  await gotoDesktop(page)
  await openLauncherApp(page, '知识库')

  const knowledgeWindow = page.locator('.desktop-window').filter({ hasText: '知识库' }).first()
  await expect(knowledgeWindow.locator('.tree-node').filter({ hasText: knowledgeDoc.filename })).toBeVisible()
  await knowledgeWindow.locator('.tree-node').filter({ hasText: knowledgeDoc.filename }).click()
  await expect(knowledgeWindow).toContainText('可以搜索、问 AI 或导出资料内容。')

  await knowledgeWindow.getByRole('button', { name: '检索' }).click()
  await knowledgeWindow.locator('.search-input').fill('source score')
  await knowledgeWindow.getByRole('button', { name: '搜索' }).click()

  const resultCard = knowledgeWindow.locator('.result-card').first()
  await expect(resultCard).toContainText(knowledgeDoc.filename)
  await expect(resultCard).toContainText('source-guide.md')
  await expect(resultCard).toContainText('段落 3')
  await expect(resultCard).toContainText('hybrid · 0.74')
  await expect(resultCard).toContainText('Knowledge search result context includes source and score fields.')

  await resultCard.getByRole('button', { name: 'metadata' }).click()
  const metadata = knowledgeWindow.locator('.result-metadata')
  await expect(metadata).toContainText('"chunk_id": 9301')
  await expect(metadata).toContainText('"source_file_id": 501')
  await expect(metadata).toContainText('"source_file": "source-guide.md"')
  await expect(metadata).toContainText('"score": 0.82')
  await expect(metadata).toContainText('"retrieval_source": "hybrid"')
})

test('agent workflow list and ledger expose evidence-critical counts and records', async ({ page }) => {
  await mockApiFallback(page)
  await mockDesktopShell(page)
  await mockAgentApis(page)
  await gotoDesktop(page)
  await openLauncherApp(page, 'AI')

  const agentWindow = page.locator('.desktop-window').filter({ hasText: 'AI' }).first()
  const detailLoaded = page.waitForResponse(response => (
    response.url().endsWith('/api/agent/workflows/77') && response.status() === 200
  ))
  await agentWindow.getByRole('button', { name: '工作流' }).click()
  await detailLoaded

  await expect(agentWindow.locator('.workflow-summary')).toContainText('总数')
  await expect(agentWindow.locator('.workflow-summary')).toContainText('失败')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('UI Full Gate workflow')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('子代理/步骤 2')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('工具 1')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('失败 1')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('产物 1')
  await expect(agentWindow.locator('.workflow-card').first()).toContainText('引用 2')
  await expect(agentWindow.locator('.workflow-detail')).toContainText('子代理验证')
  await expect(agentWindow.locator('.workflow-detail')).toContainText('artifact_id')

  const ledgerToggle = agentWindow.getByRole('button', { name: '展开账本' })
  await expect(ledgerToggle).toBeVisible()
  await ledgerToggle.click()
  const ledger = agentWindow.locator('.ledger')
  await expect(ledger).toContainText('收集证据')
  await expect(ledger).toContainText('playwright')
  await expect(ledger).toContainText('ui_gate')
  await expect(ledger).toContainText('ui_assertion_failed')
  await expect(ledger).toContainText('playwright_report')
  await expect(ledger).toContainText('workflow-evidence.png')
})
