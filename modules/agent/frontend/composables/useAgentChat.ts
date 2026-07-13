import { nextTick, onMounted, ref } from 'vue'
import { initRuntime } from '../../runtime'
import { apiFetch, apiFetchEventStream } from '../api'
import type InputArea from '../components/InputArea.vue'
import {
  collectEvidenceReferences,
  type EvidenceReference,
} from '../components/evidenceReferences'
import {
  sanitizeAssistantMessage,
  triggerDesktopRefresh,
} from '../utils/messageSanitizer'
import { normalizeRefItems, uniqueRefs } from '../utils/resourceReferences'
import { openDesktopFileFromToolResult } from '../utils/desktopFileOpen'
import type {
  AgentEntryProps,
  ConvItem,
  ModelProfile,
  MsgItem,
  RefItem,
  UsageData,
} from '../types'

export function useAgentChat(props: AgentEntryProps) {
  // ── 状态 ──
  const conversations = ref<ConvItem[]>([])
  const profiles = ref<ModelProfile[]>([])
  const tools = ref<unknown[]>([])
  const editingMessageId = ref<number | null>(null)
  const activeConvId = ref<number | null>(null)
  const messages = ref<MsgItem[]>([])
  const messagesLoading = ref(false)
  const messageLoadError = ref('')
  const inputText = ref('')
  const sending = ref(false)
  const streaming = ref(false)
  const streamingText = ref('')
  const activeAssistantStreamId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref('')
    const sidebarCollapsed = ref(false)
    const currentWorkGroup = ref<MsgItem | null>(null)
    const workLiveTimer = ref<ReturnType<typeof setInterval> | null>(null)
  const msgArea = ref<HTMLElement | null>(null)
  const inputAreaRef = ref<InstanceType<typeof InputArea> | null>(null)
  const profileKey = ref('deepseek-v4-flash')
  const showAdminPanel = ref<string | false>(false)
  const isAdmin = ref(false)

  function toggleAdminPanel(panel: string) {
    sidebarCollapsed.value = false; showAdminPanel.value = showAdminPanel.value === panel ? false : panel
  }

  // ── Edit / Inline Editing ──
  function handleStartEdit(messageId: number, _content: string) {
    editingMessageId.value = messageId || null
  }

  async function handleSubmitEdit(messageId: number, newContent: string) {
    if (!activeConvId.value || !newContent.trim()) return
    editingMessageId.value = null
    // Remove old messages after the edited message from local view
    const editIndex = messages.value.findIndex(m => m.id === messageId)
    if (editIndex >= 0) {
      messages.value = messages.value.slice(0, editIndex + 1)
      // Update the edited message content locally
      messages.value[editIndex].content = newContent
    }
    if (abortController) { abortController.abort() }
    const requestController = new AbortController()
    abortController = requestController
        clearIdleTimer()
        sending.value = true; streaming.value = true; streamingText.value = ''; activeAssistantStreamId.value = null; error.value = ''
        _pendingReferences = []

      // 编辑重发也立刻创建工作组

      currentWorkGroup.value = null
      _lastThinkingStart = 0
      ensureWorkGroup()
      scrollToBottom()
    try {
      const resp = await apiFetchEventStream(`/agent/conversations/${activeConvId.value}/messages/${messageId}/edit-resubmit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newContent, profile_key: profileKey.value }),
        signal: requestController.signal,
      })
      if (!resp.ok) { error.value = await responseErrorText(resp, `编辑请求失败 (${resp.status})`); return }
      await processStreamResponse(resp)
    } catch (e: unknown) {
      if (e instanceof DOMException && e.name === 'AbortError') { console.warn('[Agent] edit-resubmit aborted') }
      else { console.error('[Agent] edit-resubmit failed:', e); error.value = String((e as Error).message || e) }
    } finally {
      clearIdleTimer()
      sending.value = false; streaming.value = false
      if (abortController === requestController) abortController = null
      // Do NOT focus the bottom input — the edit is in-place, not a new message
    }
  }

  async function handleRollback(messageId: number) {
    if (!activeConvId.value || !messageId) return
    const ok = window.confirm('确定回退到这条消息吗？这条消息之后的对话会被移除。')
    if (!ok) return
    error.value = ''
    try {
      const result = await apiFetch<{ rolled_back: boolean }>(`/agent/conversations/${activeConvId.value}/rollback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message_id: messageId }),
      })
      if (!result.rolled_back) {
        error.value = '回退失败：消息不存在或无权限。'
        return
      }
      await reloadMessages(activeConvId.value)
    } catch (e: unknown) {
      console.error('[Agent] rollback failed:', e)
      error.value = '回退失败：' + String((e as Error).message || e)
    }
  }

  // ── Conv operations ──
  async function loadConversations() {
    conversations.value = await apiFetch<ConvItem[]>('/agent/conversations')
  }
  async function newConversation() {
    const item = await apiFetch<ConvItem>('/agent/conversations', { method: 'POST', body: JSON.stringify({ title: '新对话' }), headers: { 'Content-Type': 'application/json' } })
    conversations.value.unshift(item)
    await selectConversation(item.id)
  }
  async function renameConversation(p: ConvItem) {
    await apiFetch(`/agent/conversations/${p.id}`, { method: 'PATCH', body: JSON.stringify({ title: p.title }), headers: { 'Content-Type': 'application/json' } })
    const found = conversations.value.find(c => c.id === p.id)
    if (found) found.title = p.title
  }
  async function deleteConversation(item: ConvItem) {
    await apiFetch(`/agent/conversations/${item.id}`, { method: 'DELETE' })
    conversations.value = conversations.value.filter(c => c.id !== item.id)
    if (activeConvId.value === item.id) {
      messages.value = []; activeConvId.value = null
      // 自动选第一个剩余对话，没有就新建
      if (conversations.value.length > 0) {
        await selectConversation(conversations.value[0].id)
      } else {
        await newConversation()
      }
    }
  }

  async function selectConversation(id: number) {
    activeConvId.value = id; messages.value = []; error.value = ''; messageLoadError.value = ''; showAdminPanel.value = false
    messagesLoading.value = true
    try {
      const raw = await apiFetch<MsgItem[]>(`/agent/conversations/${id}/messages`)
      messages.value = expandTimeline(raw.map(normalizeMessageReferences))
    } catch (e: unknown) {
      console.error('[Agent] load messages failed:', e)
      messageLoadError.value = '消息加载失败：' + String((e as Error).message || e)
    } finally {
      messagesLoading.value = false
    }
    nextTick(scrollToBottom)
  }

  // ── Scroll ──
  function scrollToBottom() {
    nextTick(() => { if (msgArea.value) msgArea.value.scrollTop = msgArea.value.scrollHeight })
  }

  /** 按 timeline 展开历史消息：还原思考↔工具↔回复的真实交错顺序，并用工作组包裹 */
  function expandTimeline(msgs: MsgItem[]): MsgItem[] {
    const out: MsgItem[] = []
    for (const m of msgs) {
      const tl = m.timeline
      if (!tl || !Array.isArray(tl) || tl.length === 0) {
        out.push(m)
        continue
      }

      // 从 timeline 提取 work_summary 耗时；同时收集过程条目到工作组
      let workDurationMs = (m.usage as UsageData | null)?.work_duration_ms ?? 0
      const items: MsgItem[] = []
      let textBuf = ''

      for (const entry of tl) {
        const e = entry as Record<string, unknown>
        const entryType = e.type as string
        if (entryType === 'work_summary') {
          workDurationMs = (e.duration_ms as number) || workDurationMs
        } else if (entryType === 'schedule_overhead') {
          items.push({
            id: 0, role: '', content: '',
            eventType: 'schedule_overhead',
            label: (e.label as string) || '响应等待',
            durationMs: (e.duration_ms as number) || 0,
          } as MsgItem)
        } else if (entryType === 'thinking') {
          applyThinkingEvent((e.content as string) || '', items, { isRestore: true, durationMs: e.duration_ms as number | undefined })
        } else if (entryType === 'assistant_draft') {
          items.push({
            id: 0, role: '', content: (e.content as string) || '',
            eventType: 'assistant_draft',
            collapsed: (e.collapsed as boolean) ?? true,
            title: (e.title as string) || '回复用户',
            reason: (e.reason as string) || '',
          } as MsgItem)
        } else if (entryType === 'tool_call') {
          applyToolCallEvent((e.name as string) || 'unknown', items, e)
        } else if (entryType === 'tool_result') {
          applyToolResultEvent((e.name as string) || 'unknown', e.result, items, e.duration_ms as number | undefined, e)
        } else if (entryType === 'tool_group' || entryType === 'tool_heartbeat') {
          applyToolProgressEvent(e, items)
        } else if (entryType === 'text') {
          textBuf += (e.content as string) || ''
        }
      }

      // 恢复后保留思维内容可见，工具条目仍按工作组展示
      for (const item of items) {
        if (item.eventType === 'thinking') { item.running = false; item.collapsed = false }
      }

      const hasImageResult = items.some(item => hasImageToolResult(item.toolResult))
      if (items.length > 0) {
        out.push({
          id: 0, role: '', content: '',
          eventType: 'work_group',
          running: false,
          collapsed: false,
          durationMs: workDurationMs,
          items,
        } as MsgItem)
      }

      const content = textBuf.trim() || m.content
      if (content) {
        out.push({ id: m.id, role: m.role, content, created_at: m.created_at, thinking: '', tool_events: [], references: m.references, usage: m.usage } as MsgItem)
      } else if (items.length > 0) {
        // 工作组之后无有效内容 → 占位提示（重试后仍空回复）
        out.push({ id: m.id, role: m.role, content: '（模型未能生成回复）', created_at: m.created_at, thinking: '', tool_events: [], references: m.references, usage: null } as MsgItem)
      }
    }
    return out
  }

  function normalizeMessageReferences(message: MsgItem): MsgItem {
    const references = normalizeRefItems(message.references)
    return references.length ? { ...message, references } : { ...message, references: undefined }
  }

  function hasImageToolResult(result: unknown): boolean {
    const payload = resultPayload(result)
    if (!isRecord(payload)) return false
    if (isImageEntry(payload)) return true
    return Array.isArray(payload.images) && payload.images.some(isImageEntry)
  }

  function isImageEntry(value: unknown): value is { file_id: number; type?: string } {
    if (!isRecord(value)) return false
    if (value.type !== undefined && value.type !== 'image') return false
    return typeof value.file_id === 'number'
  }

  function resultPayload(result: unknown): unknown {
    if (!isRecord(result)) return result
    return isRecord(result.data) ? result.data : result
  }

  function isRecord(value: unknown): value is Record<string, unknown> {
    return !!value && typeof value === 'object' && !Array.isArray(value)
  }

  // ── Metadata ──
  async function loadMetadata() {
    try {
      const [p, t] = await Promise.all([
        apiFetch<ModelProfile[]>('/agent/profiles'),
        apiFetch<unknown[]>('/agent/tools'),
      ])
      profiles.value = p
      tools.value = t
    } catch (e: unknown) { error.value = '加载配置失败: ' + String((e as Error).message || e) }
  }

  // ── Chat ──
  function normalizeThinking(text: string): string {
    // The model's thinking stream arrives as small token chunks separated by
    // newlines (SSE framing).  Strip newlines without introducing extra spaces
    // (critical for Chinese where tokens can be single characters), then
    // collapse accidental multi-space runs.
    return text.replace(/[\n\r]+/g, '').replace(/[ \t]{2,}/g, ' ').trim()
  }

  // ── 共享事件处理器（流式 + 恢复 共用，防两条路径逻辑漂移） ──

  /** 处理 thinking 事件：合并到上一张卡，或新建。 */
  /** 关闭上一张思考卡并设置耗时，新建时记录开始时间 */
  let _lastThinkingStart = 0
  let _lastRoundUsage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null = null
  let _pendingReferences: RefItem[] = []
  function applyThinkingEvent(content: string, messages: MsgItem[], opts?: { isRestore?: boolean; durationMs?: number }) {
    const c = normalizeThinking(content)
    if (!c) return
    const last = messages[messages.length - 1]
    if (last && last.eventType === 'thinking') {
      last.content += c
      // 恢复时合并的时间取两者中较大值
      if (opts?.durationMs && (!last.durationMs || opts.durationMs > last.durationMs)) {
        last.durationMs = opts.durationMs
      }
    } else {
      // 把上一张思考卡关闭并算耗时
      for (let i = messages.length - 1; i >= 0; i--) {
        if (messages[i].eventType === 'thinking') {
          if (!messages[i].durationMs && _lastThinkingStart) {
            messages[i].durationMs = Date.now() - _lastThinkingStart
          }
          messages[i] = { ...messages[i], collapsed: false, running: false }
          break
        }
      }
      const isRestore = opts?.isRestore ?? false
      _lastThinkingStart = isRestore ? 0 : Date.now()
      messages.push({
        id: 0, role: '', content: c,
        eventType: 'thinking',
        collapsed: false,
        running: !isRestore,
        durationMs: opts?.durationMs ?? (isRestore ? 0 : undefined),
      } as MsgItem)
    }
  }

  /** 处理 tool_call 事件：新建工具调用卡片 */
  function applyToolCallEvent(name: string, messages: MsgItem[], event?: Record<string, unknown>) {
    messages.push({
      id: 0, role: '', content: '',
      eventType: 'tool_call',
      toolName: name || 'unknown',
      toolCallId: (event?.tool_call_id as string) || '',
      toolStatus: 'running',
    } as MsgItem)
  }

  /** 处理 tool_result 事件：合并到同名 tool_call 卡片，找不到则独立 */
  function applyToolResultEvent(name: string, result: unknown, messages: MsgItem[], durationMs?: number, event?: Record<string, unknown>, autoOpen = false) {
    let merged = false
    const toolCallId = (event?.tool_call_id as string) || ''
    const toolStatus = (event?.status as string) || ''
    const toolError = (event?.error_class as string) || (event?.failure_kind as string) || ''
    const effectiveName = (event?.effective_tool_name as string) || name || 'unknown'
    const toolReferences = eventToolReferences(event, result, effectiveName, toolStatus)
    for (let i = messages.length - 1; i >= 0; i--) {
      const sameCall = toolCallId && messages[i].toolCallId === toolCallId
      const sameName = !toolCallId && messages[i].eventType === 'tool_call' && messages[i].toolName === name
      if (messages[i].eventType === 'tool_call' && (sameCall || sameName)) {
        messages[i] = {
          ...messages[i],
          eventType: 'tool_result',
          toolName: effectiveName,
          toolResult: result,
          toolStatus,
          toolError,
          toolCallId,
          toolReferences,
          durationMs: durationMs || 0,
        }
        merged = true
        break
      }
    }
    if (!merged) {
      messages.push({
        id: 0, role: '', content: '',
        eventType: 'tool_result',
        toolName: effectiveName,
        toolResult: result,
        toolStatus,
        toolError,
        toolCallId,
        toolReferences,
        durationMs: durationMs || 0,
      } as MsgItem)
    }
    if (autoOpen) openDesktopFileFromToolResult(result)
  }

  function applyToolProgressEvent(event: Record<string, unknown>, messages: MsgItem[]) {
    const eventType = (event.type as string) || ''
    const toolCallId = (event.tool_call_id as string) || ''
    if (eventType === 'tool_group') {
      messages.push({
        id: 0,
        role: '',
        content: '',
        eventType: 'tool_progress',
        executionMode: (event.execution_mode as string) || 'serial',
        groupIndex: Number(event.group_index) || undefined,
        groupCount: Number(event.group_count) || undefined,
        toolCount: Number(event.tool_count) || undefined,
        tools: normalizeToolInfos(event.tools),
        elapsedMs: Number(event.elapsed_ms) || 0,
        toolNodes: [],
      } as MsgItem)
      return
    }

    const node: MsgItem = {
      id: 0,
      role: '',
      content: '',
      eventType: 'tool_progress_node',
      toolName: ((event.effective_tool_name as string) || (event.name as string) || 'unknown'),
      toolCallId,
      node: (event.node as string) || '',
      phase: (event.phase as string) || '',
      status: (event.status as string) || '',
      targetTool: (event.target_tool as string) || (event.effective_tool_name as string) || '',
      elapsedMs: Number(event.elapsed_ms) || 0,
    } as MsgItem

    let target: MsgItem | undefined
    for (let i = messages.length - 1; i >= 0; i--) {
      const item = messages[i]
      if (item.eventType !== 'tool_progress') continue
      if (!toolCallId) {
        target = item
        break
      }
      const hasTool = (item.tools || []).some(tool => tool.tool_call_id === toolCallId)
      if (hasTool) {
        target = item
        break
      }
    }
    if (!target) {
      target = {
        id: 0,
        role: '',
        content: '',
        eventType: 'tool_progress',
        executionMode: 'serial',
        toolCount: 1,
        tools: [{
          name: (event.name as string) || '',
          effective_tool_name: (event.effective_tool_name as string) || (event.target_tool as string) || '',
          tool_call_id: toolCallId,
        }],
        toolNodes: [],
      } as MsgItem
      messages.push(target)
    }
    target.toolNodes = [...(target.toolNodes || []), node]
    target.elapsedMs = Math.max(Number(target.elapsedMs) || 0, Number(node.elapsedMs) || 0)
  }

  function normalizeToolInfos(value: unknown): NonNullable<MsgItem['tools']> {
    if (!Array.isArray(value)) return []
    return value
      .filter(isRecord)
      .map(tool => ({
        name: typeof tool.name === 'string' ? tool.name : '',
        effective_tool_name: typeof tool.effective_tool_name === 'string' ? tool.effective_tool_name : '',
        tool_call_id: typeof tool.tool_call_id === 'string' ? tool.tool_call_id : '',
      }))
  }

  function eventToolReferences(
    event: Record<string, unknown> | undefined,
    result: unknown,
    toolName: string,
    status: string,
  ): EvidenceReference[] {
    return [
      ...collectEvidenceReferences(event?.references, { sourceTool: toolName, status }),
      ...collectEvidenceReferences(event?.result_ref, { sourceTool: toolName, status }),
      ...collectEvidenceReferences(result, { sourceTool: toolName, status }),
    ]
  }

    let abortController: AbortController | null = null
    let idleTimer: ReturnType<typeof setTimeout> | null = null
    const STREAM_IDLE_TIMEOUT_MS = 30000  // 30s 无数据自动收尾

    function clearIdleTimer() {
      if (idleTimer) { clearTimeout(idleTimer); idleTimer = null }
    }

    function resetIdleTimer(onTimeout: () => void) {
      clearIdleTimer()
      idleTimer = setTimeout(() => {
        idleTimer = null
        onTimeout()
      }, STREAM_IDLE_TIMEOUT_MS)
    }

      function stopGeneration() {
        clearIdleTimer()
        stopWorkTimer()
        closeLastThinking()
        const wg = currentWorkGroup.value
        if (wg) { wg.running = false; wg.collapsed = false }
            if (abortController) { abortController.abort(); abortController = null }
            sending.value = false
            streaming.value = false
                        streamingText.value = ''
                        activeAssistantStreamId.value = null
                        _pendingReferences = []

          }


      function stopWorkTimer() {
        if (workLiveTimer.value) { clearInterval(workLiveTimer.value); workLiveTimer.value = null }
      }

  function findAssistantStream(segmentId?: string): MsgItem | undefined {
    const id = segmentId || activeAssistantStreamId.value || ''
    return messages.value.find(m => m.role === 'assistant' && m.streaming && (!id || m.streamId === id))
  }

  function startAssistantStream(segmentId: string) {
    activeAssistantStreamId.value = segmentId
    if (findAssistantStream(segmentId)) return
    messages.value.push({
      id: 0,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      streaming: true,
      streamId: segmentId,
    })
  }

  function appendAssistantStream(segmentId: string, content: string) {
    if (!content) return
    if (!findAssistantStream(segmentId)) startAssistantStream(segmentId)
    const msg = findAssistantStream(segmentId)
    if (msg) msg.content += content
  }

  function appendVisibleToken(content: string) {
    if (!content) return
    const segmentId = activeAssistantStreamId.value || `token_stream_${Date.now()}`
    appendAssistantStream(segmentId, content)
    streamingText.value += content
  }

  function rollbackAssistantStream(segmentId: string, reason?: string) {
    // Capture the draft text before removing the streaming message
    const draftMsg = messages.value.find(m => m.role === 'assistant' && m.streaming && m.streamId === segmentId)
    const draftText = draftMsg?.content?.trim() || ''
    if (draftText) {
      const wg = ensureWorkGroup()
      if (wg && wg.items) {
        let title = '回复用户'
        let cleanReason = reason || 'rollback'
        if (cleanReason === 'tool_call_detected') title = '回复用户'
        wg.items.push({
          id: 0, role: '', content: draftText,
          eventType: 'assistant_draft',
          collapsed: true,
          title,
          reason: cleanReason,
        } as MsgItem)
      }
    }
    messages.value = messages.value.filter(m => !(m.role === 'assistant' && m.streaming && m.streamId === segmentId))
    if (activeAssistantStreamId.value === segmentId || !segmentId) activeAssistantStreamId.value = null
  }

  function commitAssistantStream(segmentId: string) {
    const msg = findAssistantStream(segmentId)
    if (!msg) return
    const sanitized = sanitizeAssistantMessage(msg.content)
    if (!sanitized.content) {
      rollbackAssistantStream(segmentId)
      return
    }
    msg.content = sanitized.content
    msg.streaming = false
    msg.eventType = undefined
    const refs = uniqueRefs([..._pendingReferences, ...(msg.references || []), ...sanitized.references])
    if (refs.length) msg.references = refs
    if (_lastRoundUsage) msg.usage = _lastRoundUsage
    _pendingReferences = []
    _lastRoundUsage = null
    if (activeAssistantStreamId.value === segmentId || !segmentId) activeAssistantStreamId.value = null
  }

  /** 将 streamingText 落成 assistant 消息 + 折叠工作组 */

        function flushStreamingAsMessage() {
          stopWorkTimer()
          closeLastThinking()
          const wg = currentWorkGroup.value
          if (wg) { wg.running = false; wg.collapsed = false }
          // 结束工作组内的思维计时，保留思维内容可见
          if (wg?.items) {
            for (const item of wg.items) {
              if (item.eventType === 'thinking') { item.collapsed = false; item.running = false }
            }
          }
          for (const m of messages.value) {
            if (m.eventType === 'thinking') { m.collapsed = false; m.running = false }
          }
          const finalText = streamingText.value.trim()
                    streamingText.value = ''
                    activeAssistantStreamId.value = null
                    commitAssistantMessage({ content: finalText, usage: _lastRoundUsage })


          _lastRoundUsage = null
          triggerDesktopRefresh()
          scrollToBottom()
        }

          function normalizeUsagePayload(evt: Record<string, unknown>): UsageData | null {
            let source: Record<string, unknown> = evt
            if (typeof evt.content === 'string' && evt.content.trim()) {
              try {
                const parsed = JSON.parse(evt.content) as Record<string, unknown>
                source = { ...parsed, ...evt }
              } catch { /* keep top-level event */ }
            }
            const promptTokens = Number(source.prompt_tokens) || 0
            const completionTokens = Number(source.completion_tokens) || 0
            const totalTokens = Number(source.total_tokens) || (promptTokens + completionTokens)
            if (!promptTokens && !completionTokens && !totalTokens) return null
            const usage: UsageData = {
              prompt_tokens: promptTokens,
              completion_tokens: completionTokens,
              total_tokens: totalTokens,
            }
            const workDurationMs = Number(source.work_duration_ms) || 0
            const workDurationSec = Number(source.work_duration_sec) || 0
            if (workDurationMs) usage.work_duration_ms = workDurationMs
            if (workDurationSec) usage.work_duration_sec = workDurationSec
            return usage
          }

          function attachUsageToLatestAssistant(usage: UsageData): boolean {
            for (let i = messages.value.length - 1; i >= 0; i--) {
              const msg = messages.value[i]
              if (msg.role === 'assistant' && msg.content.trim()) {
                msg.usage = usage
                return true
              }
            }
            return false
          }

            /** 统一 assistant 消息提交：清洗内容、判空、挂 usage */
          function commitAssistantMessage(opts: { content: string; usage?: UsageData | null; references?: RefItem[]; createdAt?: string }) {
            const sanitized = sanitizeAssistantMessage(opts.content)
            if (!sanitized.content) return
            const refs = uniqueRefs([..._pendingReferences, ...(opts.references || []), ...sanitized.references])
            const msg: MsgItem = {
              id: 0,
              role: 'assistant',
              content: sanitized.content,
              created_at: opts.createdAt || new Date().toISOString(),
            }
            if (opts.usage) { msg.usage = opts.usage }
            if (refs.length) { msg.references = refs }
            _pendingReferences = []
            messages.value.push(msg)
          }

      /** 开始/获取当前工作组 */
      function closeLastThinking() {
        const items = currentWorkGroup.value?.items ?? messages.value
        for (let i = items.length - 1; i >= 0; i--) {
          if (items[i].eventType === 'thinking') {
            if (!items[i].durationMs && _lastThinkingStart) {
              items[i].durationMs = Date.now() - _lastThinkingStart
            }
            items[i].running = false
            items[i].collapsed = false
            break
          }
        }
        _lastThinkingStart = 0
      }

      function ensureWorkGroup(): MsgItem {
        if (!currentWorkGroup.value) {
          const wg: MsgItem = {
            id: 0, role: '', content: '',
            eventType: 'work_group',
            running: true,
            collapsed: false,
            durationMs: 0,
            startedAt: Date.now(),
            items: [],
          }
          messages.value.push(wg)
          // 取回 Vue 反应式 Proxy 引用——push 后返回的是原始对象，数组元素才是 Proxy
          currentWorkGroup.value = messages.value[messages.value.length - 1]
          startWorkTimer(currentWorkGroup.value)
        }
        return currentWorkGroup.value
      }

      function startWorkTimer(wg: MsgItem) {
        stopWorkTimer()
        wg.durationMs = 0
        workLiveTimer.value = setInterval(() => {
          // 始终通过 currentWorkGroup 取 Proxy 引用，避免闭包捕获原始对象
          const g = currentWorkGroup.value
          if (g) g.durationMs = Date.now() - (g.startedAt ?? 0)
        }, 1000)
      }

        function finishWorkGroup(durationMs: number) {
          stopWorkTimer()
          // 关闭最后一张思考卡并算耗时
          closeLastThinking()
          const wg = currentWorkGroup.value
          if (wg) {
            // 计算未覆盖时间
            let accounted = 0
            if (wg.items) {
              for (const item of wg.items) {
                if (item.eventType === 'thinking' || item.eventType === 'tool_result') {
                  accounted += item.durationMs || 0
                }
              }
            }
            const overhead = durationMs - accounted
            if (overhead > 500 && wg.items) {
              wg.items.unshift({
                id: 0, role: '', content: '',
                eventType: 'schedule_overhead',
                label: '响应等待',
                durationMs: overhead,
              } as MsgItem)
            }
            wg.running = false
            wg.collapsed = false
            wg.durationMs = durationMs
          }
          currentWorkGroup.value = null
        }

        function finishWorkGroupOnError() {
          const wg = currentWorkGroup.value
          if (!wg) return
          const durationMs = wg.startedAt ? Date.now() - wg.startedAt : (wg.durationMs || 0)
          finishWorkGroup(durationMs)
        }

        function userSafeStreamError(message: string): string {
          const text = (message || '').trim()
          const lowered = text.toLowerCase()
          if (
            lowered.includes('model error') ||
            lowered.includes('all connection attempts failed') ||
            lowered.includes('stream error') ||
            lowered.includes('connection refused') ||
            lowered.includes('connecttimeout') ||
            lowered.includes('timeout')
          ) {
            return '模型服务暂时连接失败，请稍后重试。'
          }
          return text || 'AI 助手暂时无法完成回复，请稍后重试。'
        }

        async function responseErrorText(resp: Response, fallback: string): Promise<string> {
          try {
            const body = await resp.json() as { error?: unknown; message?: unknown }
            const message = typeof body.error === 'string' ? body.error : typeof body.message === 'string' ? body.message : ''
            return message ? `${fallback}: ${message}` : fallback
          } catch {
            return fallback
          }
        }

          /** 共享 SSE 流式处理核心：由 sendMessage 和 handleSubmitEdit 共用 */
          async function processStreamResponse(resp: Response) {
            if (!resp.body) { error.value = '无响应体'; return }
            const reader = resp.body.getReader()
            const decoder = new TextDecoder()
            let finished = false
            let sseBuffer = ''

            resetIdleTimer(() => {
              if (abortController) { abortController.abort() }
              error.value = '响应超时，请重试'
            })

            function handleSseBlock(block: string): boolean {
              const payloadLines: string[] = []
              for (const line of block.split('\n')) {
                const trimmed = line.trim()
                if (trimmed.startsWith('data: ')) payloadLines.push(trimmed.slice(6))
              }
              if (!payloadLines.length) return false
              const payload = payloadLines.join('\n')
                        if (payload === '[DONE]') {
                            abortController = null
                            streaming.value = false; sending.value = false
                            if (activeAssistantStreamId.value) {
                                commitAssistantStream(activeAssistantStreamId.value)
                            } else {
                                if (_lastRoundUsage) {
                                    attachUsageToLatestAssistant(_lastRoundUsage)
                                    _lastRoundUsage = null
                                }
                                flushStreamingAsMessage()
                            }
                            return true
                          }


              let evt: Record<string, unknown>
              try { evt = JSON.parse(payload) } catch { return false }
              const etype = evt.type as string | undefined

                      if (etype === 'content') {
                        abortController = null
                        streaming.value = false; sending.value = false
                        const rawContent = (evt.content as string) || ''
                        commitAssistantMessage({ content: rawContent, createdAt: new Date().toISOString(), usage: _lastRoundUsage })
                        _lastRoundUsage = null
                        return true
                      }

                      if (etype === 'assistant_stream_start') {
                        startAssistantStream((evt.segment_id as string) || `stream_${Date.now()}`)
                      } else if (etype === 'assistant_stream_delta') {
                        appendAssistantStream((evt.segment_id as string) || '', (evt.content as string) || '')
                      } else if (etype === 'assistant_stream_rollback') {
                        const segId = (evt.segment_id as string) || ''
                        const rollbackReason = (evt.reason as string) || 'rollback'
                        rollbackAssistantStream(segId, rollbackReason)
                        const replacement = (evt.replacement as string) || ''
                        streamingText.value = rollbackReason === 'summary_cleaned' ? replacement : ''
                        ensureWorkGroup()
                      } else if (etype === 'assistant_stream_commit') {
                        commitAssistantStream((evt.segment_id as string) || '')
                      } else if (etype === 'work_start') {

                ensureWorkGroup()
              } else if (etype === 'work_done') {
                const durMs = (evt.duration_ms as number) || 0
                finishWorkGroup(durMs)
              } else if (etype === 'replace') {
                let replaceContent = ''
                try {
                  const rp = typeof evt.content === 'string' ? JSON.parse(evt.content) as Record<string, unknown> : evt
                  replaceContent = (rp.content as string) || ''
                } catch { replaceContent = (evt.content as string) || '' }
                // Save pre-replace streaming text as assistant_draft if it will be overwritten
                const preReplaceText = streamingText.value.trim()
                if (preReplaceText && replaceContent !== preReplaceText) {
                  const wg = ensureWorkGroup()
                  if (wg && wg.items) {
                    wg.items.push({
                      id: 0, role: '', content: preReplaceText,
                      eventType: 'assistant_draft',
                      collapsed: true,
                      title: '回复用户',
                      reason: 'replace',
                    } as MsgItem)
                  }
                }
                streamingText.value = replaceContent
              } else if (etype === 'usage' || etype === 'round_usage') {
                const usage = normalizeUsagePayload(evt)
                if (usage) {
                  _lastRoundUsage = usage
                  if (attachUsageToLatestAssistant(usage)) {
                    _lastRoundUsage = null
                  }
                }
                const durMs = Number(evt.duration_ms) || Number(usage?.work_duration_ms) || 0
                if (durMs) finishWorkGroup(durMs)


                      } else if (etype === 'references') {
                const refs = normalizeRefItems(evt.references)
                if (refs.length) {
                  let attached = false
                  for (let i = messages.value.length - 1; i >= 0; i--) {
                    if (messages.value[i].role === 'assistant') {
                      messages.value[i].references = uniqueRefs([...(messages.value[i].references || []), ...refs])
                      attached = true
                      break
                    }
                  }
                  if (!attached) {
                    _pendingReferences = uniqueRefs([..._pendingReferences, ...refs])
                  }
                }

              } else if (etype === 'thinking') {
                ensureWorkGroup()
                applyThinkingEvent(evt.content as string || '', currentWorkGroup.value?.items ?? messages.value, { isRestore: false })
                } else if (etype === 'tool_call') {
                  ensureWorkGroup()
                  applyToolCallEvent(evt.name as string || 'unknown', currentWorkGroup.value?.items ?? messages.value, evt)
                } else if (etype === 'tool_group' || etype === 'tool_heartbeat') {
                  ensureWorkGroup()
                  applyToolProgressEvent(evt, currentWorkGroup.value?.items ?? messages.value)
                } else if (etype === 'tool_result') {
                  ensureWorkGroup()
                  applyToolResultEvent(evt.name as string || 'unknown', evt.result, currentWorkGroup.value?.items ?? messages.value, evt.duration_ms as number | undefined, evt, true)
                      } else if (etype === 'token') {
                        if (activeAssistantStreamId.value) {
                          appendAssistantStream(activeAssistantStreamId.value, (evt.content as string) || '')
                        } else {
                          appendVisibleToken((evt.content as string) || '')
                        }
                      } else if (etype === 'error') {

                streaming.value = false; sending.value = false
                finishWorkGroupOnError()
                error.value = userSafeStreamError((evt.content as string) || '')
                void reader.cancel().catch(() => {})
                return true
              }

              scrollToBottom()
              return false
            }

            while (!finished) {
              let done = false; let value: Uint8Array | undefined
              try { const r = await reader.read(); done = r.done; value = r.value } catch { break }
              if (done) {
                sseBuffer += decoder.decode()
                if (sseBuffer.trim()) {
                  finished = handleSseBlock(sseBuffer)
                }
                    if (!finished) {
                          abortController = null
                          streaming.value = false; sending.value = false
                          if (activeAssistantStreamId.value) {
                              commitAssistantStream(activeAssistantStreamId.value)
                          } else {
                              if (_lastRoundUsage) {
                                  attachUsageToLatestAssistant(_lastRoundUsage)
                                  _lastRoundUsage = null
                              }
                              flushStreamingAsMessage()
                          }
                          finished = true

                        }
                break
              }
              resetIdleTimer(() => {
                if (abortController) { abortController.abort() }
                error.value = '响应超时，请重试'
              })
              sseBuffer += decoder.decode(value, { stream: true })
              const blocks = sseBuffer.split(/\r?\n\r?\n/)
              sseBuffer = blocks.pop() ?? ''
              for (const block of blocks) {
                if (handleSseBlock(block)) {
                  finished = true
                  break
                }
              }
            }
          }


        async function sendMessage() {
          if (sending.value || !activeConvId.value) return
          const text = inputText.value.trim()
          if (!text) return
          if (abortController) { abortController.abort() }
          const requestController = new AbortController()
          abortController = requestController
          clearIdleTimer()
          inputText.value = ''
            sending.value = true; streaming.value = true; streamingText.value = ''; activeAssistantStreamId.value = null; error.value = ''
            _pendingReferences = []
            messages.value.push({ id: 0, role: 'user', content: text, created_at: new Date().toISOString() })

          // 立刻创建工作组并开始计时——不等后端 work_start
          currentWorkGroup.value = null
          _lastThinkingStart = 0
          ensureWorkGroup()
          scrollToBottom()
          try {
            const resp = await apiFetchEventStream('/agent/chat', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ conversation_id: activeConvId.value, content: text, profile_key: profileKey.value }),
              signal: requestController.signal,
            })
            if (!resp.ok) { error.value = await responseErrorText(resp, `请求失败 (${resp.status})`); return }
            await processStreamResponse(resp)
          } catch (e: unknown) {
            if (e instanceof DOMException && e.name === 'AbortError') { console.warn('[Agent] fetch aborted (stop/timeout)') }
            else { console.error('[Agent] fetch failed:', e); error.value = String((e as Error).message || e) }
          } finally {
            clearIdleTimer()
            sending.value = false; streaming.value = false
            if (abortController === requestController) abortController = null
            inputAreaRef.value?.focus()
          }
        }

  async function reloadMessages(convId: number) {
    messageLoadError.value = ''
    messagesLoading.value = true
    try {
      const raw = await apiFetch<MsgItem[]>(`/agent/conversations/${convId}/messages`)
      messages.value = expandTimeline(raw.map(normalizeMessageReferences))
    } catch (e: unknown) {
      console.error('[Agent] reload messages failed:', e)
      messageLoadError.value = '消息加载失败：' + String((e as Error).message || e)
    } finally {
      messagesLoading.value = false
    }
  }

  onMounted(async () => {
    await initRuntime('agent')
    await Promise.all([loadMetadata(), loadConversations()])
    if (conversations.value.length === 0) await newConversation()
    else await selectConversation(conversations.value[0].id)

    // 判断当前用户是否为 admin（用于显示引擎面板按钮）
    try {
      const userInfo = await apiFetch<{ role: string }>('/current-user')
      isAdmin.value = userInfo.role === 'admin'
    } catch { /* 非 admin 不显示按钮 */ }

    // 预填上下文（来自其他模块如知识库的"问 AI"调用）
    if (props.prefill) {
      const parts: string[] = []
      if (props.prefill.documentName) {
        parts.push(`关于「${props.prefill.documentName}」`)
      }
      if (props.prefill.question) {
        parts.push(props.prefill.question)
      }
      if (parts.length) {
        inputText.value = parts.join('，')
        nextTick(() => inputAreaRef.value?.focus())
      }
    }
  })

  return {
    conversations,
    activeConvId,
    loading,
    sidebarCollapsed,
    isAdmin,
    showAdminPanel,
    toggleAdminPanel,
    selectConversation,
    newConversation,
    renameConversation,
    deleteConversation,
    messages,
    msgArea,
    messageLoadError,
    reloadMessages,
    messagesLoading,
    editingMessageId,
    handleStartEdit,
    handleSubmitEdit,
    handleRollback,
    inputAreaRef,
    inputText,
    sending,
    sendMessage,
    stopGeneration,
    error,
  }
}
