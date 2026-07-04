<template>
  <div class="agent-app agent-theme">
    <ConversationSidebar
      :conversations="conversations"
      :activeConvId="activeConvId"
      :loading="loading"
      :collapsed="sidebarCollapsed"
      :isAdmin="isAdmin"
      :adminActive="showAdminPanel || undefined"
      @select="selectConversation"
      @new="newConversation"
      @rename="renameConversation"
      @delete="deleteConversation"
      @toggle="sidebarCollapsed = !sidebarCollapsed"
      @admin="toggleAdminPanel"
    />

    <EnginePanel v-if="showAdminPanel === 'engine'" class="agent-main" />
    <AgentConfigPanel v-else-if="showAdminPanel === 'config'" class="agent-main" />
    <ApprovalPanel v-else-if="showAdminPanel === 'approvals'" class="agent-main" />
    <WorkflowList v-else-if="showAdminPanel === 'workflows'" class="agent-main" :is-admin="isAdmin" @open-approvals="toggleAdminPanel('approvals')" />

    <section v-else class="agent-main">
	      <!-- 消息区域 -->
      <div class="msg-area" ref="msgArea">
        <div v-if="!activeConvId && !loading" class="msg-empty">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1" width="40" height="40" class="msg-empty-icon">
            <circle cx="24" cy="24" r="20"/><path d="M24 16v12M18 22h12"/><path d="M16 32l3-3h10l3 3"/>
          </svg>
          <p>选择或创建一个对话开始</p>
        </div>
        <div v-if="messageLoadError" class="msg-load-error" role="alert">
          <span>{{ messageLoadError }}</span>
          <button type="button" @click="activeConvId && reloadMessages(activeConvId)">重试</button>
        </div>
        <div v-else-if="messagesLoading" class="msg-load-state">消息加载中...</div>
        <div v-else-if="messages.length === 0 && activeConvId && !loading" class="msg-empty">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1" width="40" height="40" class="msg-empty-icon">
            <path d="M8 10h32v24H16l-8 6V10z"/>
          </svg>
          <p>开始对话吧</p>
          <span class="msg-empty-hint">发送消息开启对话</span>
        </div>

        <template v-for="(m, i) in messages" :key="`${m.id}-${i}`">
          <WorkTraceGroup v-if="m.eventType === 'work_group'" :message="m" />
          <ToolCallCard v-else-if="m.eventType === 'tool_call' || m.eventType === 'tool_result'" :message="m" />
          <ThinkingCard v-else-if="m.eventType === 'thinking'" :content="m.content" :running="m.running" :collapsed="m.collapsed" :durationMs="m.durationMs" />
          <MessageBubble v-else :message="m" :editingId="editingMessageId" :streaming="m.streaming" @edit="handleStartEdit" @submitEdit="handleSubmitEdit" @rollback="handleRollback" />
        </template>
      </div>

      <InputArea ref="inputAreaRef" v-model="inputText" :sending="sending" @send="sendMessage" @stop="stopGeneration" />

      <p v-if="error" class="error-text">{{ error }}</p>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, nextTick, onMounted } from 'vue'
import { initRuntime } from '../runtime'
import { apiFetch, apiFetchRaw } from './api'
import ConversationSidebar from './components/ConversationSidebar.vue'

import InputArea from './components/InputArea.vue'
import MessageBubble from './components/MessageBubble.vue'
import ThinkingCard from './components/ThinkingCard.vue'
import ToolCallCard from './components/ToolCallCard.vue'
import WorkTraceGroup from './components/WorkTraceGroup.vue'
import WorkflowList from './components/WorkflowList.vue'
import EnginePanel from './admin/EnginePanel.vue'
import AgentConfigPanel from './admin/AgentConfigPanel.vue'
import ApprovalPanel from './admin/ApprovalPanel.vue'
import {
  collectEvidenceReferences,
  type EvidenceReference,
} from './components/evidenceReferences'
import './components/style-variables.css'

// ── 类型 ──
interface ConvItem { id: number; title: string; status?: string }
interface ModelProfile { key: string; name: string; provider: string; model: string }
interface RefItem { type: string; title: string; source: string; excerpt: string; url?: string }
interface ApiBody<T> { success: boolean; data: T; error?: string | null }
interface UsageData {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  work_duration_ms?: number
  work_duration_sec?: number
  [key: string]: unknown
}
interface MsgItem {
  id: number
  role: string
  content: string
  created_at?: string | null
  eventType?: string
	  toolName?: string
	  toolResult?: unknown
	  toolStatus?: string
	  toolError?: string
	  toolCallId?: string
	  toolReferences?: EvidenceReference[]
	  thinking?: string
  references?: RefItem[]
  tool_events?: unknown[]
  timeline?: unknown[]
  usage?: UsageData | null
  collapsed?: boolean
  running?: boolean
  durationMs?: number
  startedAt?: number
  items?: MsgItem[]
  streaming?: boolean
  streamId?: string
}

interface SanitizedMessage {
  content: string
  references: RefItem[]
}

interface DesktopEventWindow extends Window {
  __DESKTOP_EVENT_BUS__?: { emit: (name: string, payload: Record<string, unknown>) => void }
}

// ── Props（外部模块传入的预填上下文） ──
const props = defineProps<{
  prefill?: { documentId?: number; documentName?: string; question?: string }
}>()

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
  abortController = new AbortController()
			clearIdleTimer()
			sending.value = true; streaming.value = true; streamingText.value = ''; activeAssistantStreamId.value = null; error.value = ''
			_pendingReferences = []

		// 编辑重发也立刻创建工作组

	  currentWorkGroup.value = null
	  _lastThinkingStart = 0
	  ensureWorkGroup()
	  scrollToBottom()
  try {
    const resp = await apiFetchRaw(`/agent/conversations/${activeConvId.value}/messages/${messageId}/edit-resubmit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content: newContent, profile_key: profileKey.value }),
      signal: abortController.signal,
    })
    if (!resp.ok) { error.value = `编辑请求失败 (${resp.status})`; return }
    await processStreamResponse(resp)
  } catch (e: unknown) {
    if (e instanceof DOMException && e.name === 'AbortError') { console.warn('[Agent] edit-resubmit aborted') }
    else { console.error('[Agent] edit-resubmit failed:', e); error.value = String((e as Error).message || e) }
  } finally {
    clearIdleTimer()
    sending.value = false; streaming.value = false
    abortController = null
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
    messages.value = expandTimeline(raw)
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
      } else if (entryType === 'text') {
        textBuf += (e.content as string) || ''
      }
    }

    // 恢复时折叠所有思考/工具条目
    for (const item of items) {
      if (item.eventType === 'thinking') { item.running = false; item.collapsed = true }
    }

    if (items.length > 0) {
      out.push({
        id: 0, role: '', content: '',
        eventType: 'work_group',
        running: false,
        collapsed: true,
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

/** 处理 thinking 事件：合并到上一张卡，或新建。isRestore 控制初始折叠。 */
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
        messages[i] = { ...messages[i], collapsed: true, running: false }
        break
      }
    }
    const isRestore = opts?.isRestore ?? false
    _lastThinkingStart = isRestore ? 0 : Date.now()
    messages.push({
      id: 0, role: '', content: c,
      eventType: 'thinking',
      collapsed: isRestore,
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
function applyToolResultEvent(name: string, result: unknown, messages: MsgItem[], durationMs?: number, event?: Record<string, unknown>) {
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
		  if (wg) { wg.running = false; wg.collapsed = true }
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
			  if (wg) { wg.running = false; wg.collapsed = true }
			  // 也折叠工作组内的思考和工具条目
			  if (wg?.items) {
			    for (const item of wg.items) {
			      if (item.eventType === 'thinking') { item.collapsed = true; item.running = false }
			    }
			  }
			  for (const m of messages.value) {
			    if (m.eventType === 'thinking') { m.collapsed = true; m.running = false }
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

				function normalizeRefTitle(title: string): string {
				  return title.replace(/^\d+[.)、]\s*/, '').trim()
				}

				function uniqueRefs(refs: RefItem[]): RefItem[] {
				  const seen = new Set<string>()
				  const out: RefItem[] = []
				  for (const ref of refs) {
				    const key = ref.url || `${ref.type}:${ref.title || ref.source || ''}`
				    if (!key || seen.has(key)) continue
				    seen.add(key)
				    out.push(ref)
				  }
				  return out
				}

				function sanitizeAssistantMessage(text: string): SanitizedMessage {
				  let content = cleanXmlContent(text)
				  content = content.replace(/<p>\s*<strong>\s*最佳路径总结[:：]\s*<\/strong>[\s\S]*?<\/p>/gi, '')
				  content = content.replace(/(?:^|\n)\s*(?:\*\*)?最佳路径总结[:：](?:\*\*)?[\s\S]*?(?=\n\s*📎\s*来源[:：]|\n\s*#{1,6}\s|\n\s*[-*]\s|$)/gi, '\n')
				  const references: RefItem[] = []
				  const htmlSourceMatch = content.match(/<p>\s*📎\s*来源[:：]?\s*<\/p>\s*<ul>([\s\S]*?)<\/ul>/i)
				  const markdownSourceMatch = content.match(/(?:^|\n)\s*📎\s*来源[:：]?\s*\n?([\s\S]*)$/)
				  const sourceBlock = htmlSourceMatch?.[1] || markdownSourceMatch?.[1] || ''
				  if (sourceBlock) {
				    const linkRe = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)|<a\s+[^>]*href=["'](https?:\/\/[^"']+)["'][^>]*>(.*?)<\/a>/gi
				    let m: RegExpExecArray | null
				    while ((m = linkRe.exec(sourceBlock)) !== null) {
				      const title = normalizeRefTitle((m[1] || m[4] || m[2] || m[3] || '').replace(/<[^>]+>/g, ''))
				      const url = m[2] || m[3]
				      if (title || url) references.push({ type: 'web', title: title || url, source: title || url, excerpt: '', url })
				    }
				    if (references.length) {
				      if (htmlSourceMatch?.[0]) {
				        content = content.replace(htmlSourceMatch[0], '').trim()
				      } else if (markdownSourceMatch) {
				        content = content.slice(0, markdownSourceMatch.index).trim()
				      }
				    }
				  }
				  return { content: content.trim(), references: uniqueRefs(references) }
				}

				/** 兜底清洗：移除内容中残留的工具调用标记 */

				function cleanXmlContent(text: string): string {
				  const normalized = text
				    .replace(/<｜｜DSML｜｜/g, '<')
				    .replace(/<\/｜｜DSML｜｜/g, '</')
				  return normalized
				    .replace(/<\w*:?tool_calls?[\s\S]*?<\/\w*:?tool_calls?\s*>/gi, '')
				    .replace(/<\w*:?invoke[\s\S]*?<\/\w*:?invoke\s*>/gi, '')
				    .replace(/\n{3,}/g, '\n\n')
				    .trim()
				}


				/** 通知桌面 Shell 刷新文件列表 */
				function triggerDesktopRefresh() {
				  try {
				    const eventWindow = window as DesktopEventWindow
				    // 通过 mitt event bus 发射刷新事件
				    if (eventWindow.__DESKTOP_EVENT_BUS__) {
				      eventWindow.__DESKTOP_EVENT_BUS__.emit('refresh:file-list', {})
				    }
				    // 备用：手动触发 custom event
				    window.dispatchEvent(new CustomEvent('desktop:refresh-files'))
				  } catch { /* 非关键 */ }
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
		      items[i].collapsed = true
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
			    wg.collapsed = true
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
                          void reader.cancel().catch(() => {})
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
                      void reader.cancel().catch(() => {})
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
				      const refs = Array.isArray(evt.references) ? evt.references as RefItem[] : []
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
					    } else if (etype === 'tool_result') {
					      ensureWorkGroup()
					      applyToolResultEvent(evt.name as string || 'unknown', evt.result, currentWorkGroup.value?.items ?? messages.value, evt.duration_ms as number | undefined, evt)
                    } else if (etype === 'token') {
                      if (activeAssistantStreamId.value) {
                        appendAssistantStream(activeAssistantStreamId.value, (evt.content as string) || '')
                      } else {
                        streamingText.value += evt.content as string || ''
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
			  abortController = new AbortController()
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
			    const resp = await apiFetchRaw('/agent/chat', {
			      method: 'POST',
			      headers: { 'Content-Type': 'application/json' },
			      body: JSON.stringify({ conversation_id: activeConvId.value, content: text, profile_key: profileKey.value }),
			      signal: abortController.signal,
			    })
			    if (!resp.ok) { error.value = `请求失败 (${resp.status})`; return }
			    await processStreamResponse(resp)
			  } catch (e: unknown) {
			    if (e instanceof DOMException && e.name === 'AbortError') { console.warn('[Agent] fetch aborted (stop/timeout)') }
			    else { console.error('[Agent] fetch failed:', e); error.value = String((e as Error).message || e) }
			  } finally {
			    clearIdleTimer()
			    sending.value = false; streaming.value = false
			    abortController = null
			    inputAreaRef.value?.focus()
			  }
			}

async function reloadMessages(convId: number) {
  messageLoadError.value = ''
  messagesLoading.value = true
  try {
    const raw = await apiFetch<MsgItem[]>(`/agent/conversations/${convId}/messages`)
    messages.value = expandTimeline(raw)
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
</script>

<style scoped>
.agent-app { display: flex; height: 100%; overflow: hidden; }
.agent-main { flex: 1; display: flex; flex-direction: column; min-width: 0; position: relative; background: var(--ag-bg-page); }

/* ── Messages ── */
.msg-area { flex: 1; overflow-y: auto; padding: var(--ag-space-xl) var(--ag-space-lg); display: flex; flex-direction: column; }
.msg-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; color: var(--ag-text-tertiary); gap: var(--ag-space-sm); }
.msg-empty-icon { opacity: 0.25; }
.msg-empty p { margin: 0; font-size: var(--ag-font-size-md); }
.msg-empty-hint { font-size: var(--ag-font-size-sm); }
.msg-load-state {
  padding: var(--ag-space-lg);
  text-align: center;
  color: var(--ag-text-tertiary);
  font-size: var(--ag-font-size-sm);
}
.msg-load-error {
  margin: var(--ag-space-md);
  padding: var(--ag-space-sm) var(--ag-space-md);
  border: 1px solid rgba(229, 83, 75, 0.32);
  border-radius: var(--ag-radius-md);
  background: rgba(254, 240, 238, 0.92);
  color: #b42318;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--ag-space-sm);
  font-size: var(--ag-font-size-sm);
}
.msg-load-error button {
  flex: none;
  height: 28px;
  border: 1px solid currentColor;
  border-radius: var(--ag-radius-sm);
  background: #fff;
  color: inherit;
  cursor: pointer;
}

/* ── Streaming row ── */
.msg-row.streaming { flex-shrink: 0; display: flex; gap: var(--ag-space-md); margin-bottom: var(--ag-space-xl); animation: msgSlideUp 0.25s ease-out; }
@keyframes msgSlideUp { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.streaming-ai { display: flex; gap: var(--ag-space-md); max-width: 85%; }
.streaming-content { display: flex; align-items: flex-start; gap: 2px; padding: var(--ag-space-md) var(--ag-space-lg); border-radius: var(--ag-radius-sm) var(--ag-radius-xl) var(--ag-radius-xl) var(--ag-radius-xl); background: var(--ag-bg-assistant-msg); border: 1px solid var(--ag-border-light); box-shadow: var(--ag-shadow-sm); font-size: var(--ag-font-size-md); line-height: var(--ag-line-height-relaxed); min-width: 80px; }
.streaming-text { white-space: pre-wrap; word-break: break-word; }
.streaming-cursor { animation: blink 1s step-end infinite; color: var(--ag-primary); font-weight: 700; }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }

/* ── Shared avatar (for streaming) ── */
.msg-avatar { flex-shrink: 0; width: 32px; height: 32px; border-radius: var(--ag-radius-full); display: flex; align-items: center; justify-content: center; margin-top: 2px; }
.msg-avatar.assistant { background: var(--ag-primary-light); color: var(--ag-primary); }

/* ── Error ── */
.error-text { margin: 0; padding: var(--ag-space-sm) var(--ag-space-lg) var(--ag-space-md); color: var(--ag-error); font-size: var(--ag-font-size-sm); background: var(--ag-bg-base); }
</style>
