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

    <section v-else class="agent-main">
	      <!-- 消息区域 -->
      <div class="msg-area" ref="msgArea">
        <div v-if="!activeConvId && !loading" class="msg-empty">
          <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1" width="40" height="40" class="msg-empty-icon">
            <circle cx="24" cy="24" r="20"/><path d="M24 16v12M18 22h12"/><path d="M16 32l3-3h10l3 3"/>
          </svg>
          <p>选择或创建一个对话开始</p>
        </div>
        <div v-if="messages.length === 0 && activeConvId && !loading" class="msg-empty">
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
          <MessageBubble v-else :message="m" :editingId="editingMessageId" @edit="handleStartEdit" @submitEdit="handleSubmitEdit" />
        </template>

        <!-- 流式输出指示器 -->
        <div v-if="streaming" class="msg-row streaming">
          <div class="streaming-ai">
            <div class="msg-avatar assistant">
              <svg viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
                <path d="M10 2C5.58 2 2 4.46 2 7.5c0 1.86 1.18 3.5 3 4.5v3l3.34-2.01c.52.14 1.08.22 1.66.22 4.42 0 8-2.46 8-5.5S14.42 2 10 2z"/>
              </svg>
            </div>
            <div class="streaming-content">
              <div class="streaming-text">{{ streamingText || '思考中...' }}</div>
              <span class="streaming-cursor">|</span>
            </div>
          </div>
        </div>
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
import EnginePanel from './admin/EnginePanel.vue'
import AgentConfigPanel from './admin/AgentConfigPanel.vue'
import ApprovalPanel from './admin/ApprovalPanel.vue'
import './components/style-variables.css'

// ── 类型 ──
interface ConvItem { id: number; title: string; status?: string }
interface ModelProfile { key: string; name: string; provider: string; model: string }
interface RefItem { type: string; title: string; source: string; excerpt: string; url?: string }
interface ApiBody<T> { success: boolean; data: T; error?: string | null }
interface UsageData { work_duration_ms?: number; work_duration_sec?: number; [key: string]: unknown }
interface MsgItem {
  id: number
  role: string
  content: string
  created_at?: string | null
  eventType?: string
  toolName?: string
  toolResult?: unknown
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
const inputText = ref('')
const sending = ref(false)
const streaming = ref(false)
const streamingText = ref('')
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
	  sending.value = true; streaming.value = true; streamingText.value = ''; error.value = ''
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
  activeConvId.value = id; messages.value = []; error.value = ''; showAdminPanel.value = false
  try {
    const raw = await apiFetch<MsgItem[]>(`/agent/conversations/${id}/messages`)
    messages.value = expandTimeline(raw)
  } catch { /* ignore */ }
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
      } else if (entryType === 'tool_call') {
        applyToolCallEvent((e.name as string) || 'unknown', items)
      } else if (entryType === 'tool_result') {
        applyToolResultEvent((e.name as string) || 'unknown', e.result, items, e.duration_ms as number | undefined)
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
function applyToolCallEvent(name: string, messages: MsgItem[]) {
  messages.push({
    id: 0, role: '', content: '',
    eventType: 'tool_call',
    toolName: name || 'unknown',
  } as MsgItem)
}

/** 处理 tool_result 事件：合并到同名 tool_call 卡片，找不到则独立 */
function applyToolResultEvent(name: string, result: unknown, messages: MsgItem[], durationMs?: number) {
  let merged = false
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].eventType === 'tool_call' && messages[i].toolName === name) {
      messages[i] = { ...messages[i], eventType: 'tool_result', toolResult: result, durationMs: durationMs || 0 }
      merged = true
      break
    }
  }
  if (!merged) {
    messages.push({
      id: 0, role: '', content: '',
      eventType: 'tool_result',
      toolName: name || 'unknown',
      toolResult: result,
      durationMs: durationMs || 0,
    } as MsgItem)
  }
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
		}

		function stopWorkTimer() {
		  if (workLiveTimer.value) { clearInterval(workLiveTimer.value); workLiveTimer.value = null }
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
			  if (finalText) {
			    // 兜底清洗：移除残留的 <invoke> XML 标记
			    const cleanText = cleanXmlContent(finalText)
			    const msg: MsgItem = { id: 0, role: 'assistant', content: cleanText, created_at: new Date().toISOString() }
			    if (_lastRoundUsage) { msg.usage = _lastRoundUsage as UsageData }
			    messages.value.push(msg)
			    _lastRoundUsage = null
			  }
				  triggerDesktopRefresh()
				  scrollToBottom()
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
			    const w = window as any
			    // 通过 mitt event bus 发射刷新事件
			    if (w.__DESKTOP_EVENT_BUS__) {
			      w.__DESKTOP_EVENT_BUS__.emit('refresh:file-list', {})
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

			/** 共享 SSE 流式处理核心：由 sendMessage 和 handleSubmitEdit 共用 */
			async function processStreamResponse(resp: Response) {
			  if (!resp.body) { error.value = '无响应体'; return }
			  const reader = resp.body.getReader()
			  const decoder = new TextDecoder()
			  let finished = false

			  resetIdleTimer(() => {
			    if (abortController) { abortController.abort() }
			    error.value = '响应超时，请重试'
			  })

			  while (!finished) {
			    let done = false; let value: Uint8Array | undefined
			    try { const r = await reader.read(); done = r.done; value = r.value } catch { break }
			    if (done) {
			      abortController = null
			      streaming.value = false; sending.value = false
			      flushStreamingAsMessage()
			      finished = true
			      break
			    }
			    resetIdleTimer(() => {
			      if (abortController) { abortController.abort() }
			      error.value = '响应超时，请重试'
			    })
			    const chunk = decoder.decode(value!, { stream: true })
			    for (const line of chunk.split('\n')) {
			      const trimmed = line.trim()
			      if (!trimmed.startsWith('data: ')) continue
			      const payload = trimmed.slice(6)
			      if (payload === '[DONE]') {
			        abortController = null
			        streaming.value = false; sending.value = false
			        flushStreamingAsMessage()
			        finished = true
			        reader.cancel().catch(() => {})
			        break
			      }
			      let evt: Record<string, unknown>
			      try { evt = JSON.parse(payload) } catch { continue }
			      const etype = evt.type as string | undefined

			      if (etype === 'content') {
			        abortController = null
			        streaming.value = false; sending.value = false
			        const rawContent = (evt.content as string) || ''
			        messages.value.push({ id: 0, role: 'assistant', content: cleanXmlContent(rawContent), created_at: new Date().toISOString() })
			        finished = true
			        reader.cancel().catch(() => {})
			        break
			      }

			      if (etype === 'work_start') {
			        ensureWorkGroup()
			      }
			      else if (etype === 'work_done') {
			        const durMs = (evt.duration_ms as number) || 0
			        finishWorkGroup(durMs)
			      }
			      else if (etype === 'replace') {
			        // 内联工具调用恢复：替换流式回复中的 XML
			        let replaceContent = ''
			        try {
			          const rp = typeof evt.content === 'string' ? JSON.parse(evt.content) : evt
			          replaceContent = (rp as Record<string, unknown>).content as string || ''
			        } catch { replaceContent = (evt.content as string) || '' }
			        if (replaceContent) {
			          streamingText.value = replaceContent
			        }
			      }
				      else if (etype === 'usage') {
				        const wg = currentWorkGroup.value
				        if (wg && evt.content) {
				          try {
				            const u = typeof evt.content === 'string' ? JSON.parse(evt.content) : evt
				            const durMs = (u as Record<string, unknown>).work_duration_ms as number
				            if (durMs) finishWorkGroup(durMs)
				          } catch { /* ignore */ }
				        }
				      }
					      else if (etype === 'round_usage') {
					        // 整轮累积 token 数：存到最近一条 assistant 消息的 usage 字段
					        const u = evt as Record<string, unknown>
					        const pt = Number(u.prompt_tokens) || 0
					        const ct = Number(u.completion_tokens) || 0
					        const tt = Number(u.total_tokens) || 0
					        if (pt || ct || tt) {
					          _lastRoundUsage = { prompt_tokens: pt, completion_tokens: ct, total_tokens: tt }
					        }
					      }
					      else if (etype === 'references') {
					        const refs = Array.isArray(evt.references) ? evt.references as RefItem[] : []
					        if (refs.length) {
					          for (let i = messages.value.length - 1; i >= 0; i--) {
					            if (messages.value[i].role === 'assistant') {
					              messages.value[i].references = refs
					              break
					            }
					          }
					        }
					      }
			      else if (etype === 'thinking') {

			        ensureWorkGroup()
			        applyThinkingEvent(evt.content as string || '', currentWorkGroup.value?.items ?? messages.value, { isRestore: false })
			      }
			      else if (etype === 'tool_call') {
			        ensureWorkGroup()
			        applyToolCallEvent(evt.name as string || 'unknown', currentWorkGroup.value?.items ?? messages.value)
			      }
			      else if (etype === 'tool_result') {
			        ensureWorkGroup()
			        applyToolResultEvent(evt.name as string || 'unknown', evt.result, currentWorkGroup.value?.items ?? messages.value, evt.duration_ms as number | undefined)
			      }
			      else if (etype === 'token') { streamingText.value += evt.content as string || '' }
			      else if (etype === 'error') { streaming.value = false; sending.value = false; error.value = (evt.content as string) || '流式错误'; finished = true; reader.cancel().catch(() => {}); break }
			      scrollToBottom()
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
			  sending.value = true; streaming.value = true; streamingText.value = ''; error.value = ''
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

async function reloadMessages(convId: number) { try { const raw = await apiFetch<MsgItem[]>(`/agent/conversations/${convId}/messages`); messages.value = expandTimeline(raw) } catch { /* ignore */ } }

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
