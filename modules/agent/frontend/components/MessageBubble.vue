<template>
  <div class="msg-row" :class="[message.role]">
    <div class="msg-avatar" :class="message.role">
      <svg v-if="message.role === 'user'" viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
        <path d="M10 10c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v1h16v-1c0-2.66-5.33-4-8-4z"/>
      </svg>
      <svg v-else viewBox="0 0 20 20" fill="currentColor" width="18" height="18">
        <path d="M10 2C5.58 2 2 4.46 2 7.5c0 1.86 1.18 3.5 3 4.5v3l3.34-2.01c.52.14 1.08.22 1.66.22 4.42 0 8-2.46 8-5.5S14.42 2 10 2z"/>
      </svg>
    </div>
    <div class="msg-card">
      <!-- 思维过程（在气泡上方） -->
      <div v-if="message.thinking" class="inline-thinking">
        <button class="inline-th-toggle" @click="showThinking = !showThinking">
          <span class="th-indicator"></span>
          <span>思维过程</span>
          <svg :class="{ rotated: showThinking }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
            <path d="M4 3l4 3-4 3"/>
          </svg>
        </button>
        <div v-show="showThinking" class="inline-th-body">{{ normalizedThinking }}</div>
      </div>

      <!-- 工具记录（思考之后、气泡之前） -->
      <div v-if="message.tool_events?.length" class="inline-tools">
        <button class="inline-tools-toggle" @click="showTools = !showTools">
          <span class="tools-dot"></span>
          <span>工具记录 {{ message.tool_events.length }}</span>
          <svg :class="{ rotated: showTools }" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.5" width="10" height="10">
            <path d="M4 3l4 3-4 3"/>
          </svg>
        </button>
        <div v-show="showTools" class="inline-tools-body">
          <pre>{{ formatToolResult(message.tool_events) }}</pre>
        </div>
      </div>

      <!-- 工作耗时 -->
      <div v-if="message.usage?.work_duration_sec && message.role === 'assistant'" class="work-duration">
        已工作 {{ message.usage.work_duration_sec }} 秒
      </div>

      <div class="msg-bubble" :class="message.role">
        <div v-if="isEditing" class="msg-edit-area">
          <textarea ref="editTextarea" v-model="editText" class="msg-edit-input" @keydown.escape="cancelEdit" @keydown.enter.ctrl="submitEdit"></textarea>
          <div class="msg-edit-actions">
            <button class="msg-edit-ok" @click="submitEdit">发送</button>
            <button class="msg-edit-cancel" @click="cancelEdit">取消</button>
          </div>
        </div>
        <div v-else-if="message.role === 'assistant'" class="msg-md" v-html="renderedContent" @click="onMsgMdClick"></div>
        <div v-else class="msg-text">{{ message.content }}</div>
      </div>

      <div class="msg-footer">
        <time class="msg-time">{{ formatTime(message.created_at) }}</time>
        <span v-if="message.usage" class="msg-usage">
          <span>入{{ message.usage.prompt_tokens }} 出{{ message.usage.completion_tokens }} 总计{{ message.usage.total_tokens }}</span>
        </span>
        <span class="msg-actions">
          <button class="msg-action-btn" title="复制" @click="copyContent">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><rect x="4" y="4" width="10" height="10" rx="1"/><path d="M12 4V3a1 1 0 00-1-1H3a1 1 0 00-1 1v8a1 1 0 001 1h1"/></svg>
          </button>
          <button v-if="message.role === 'user' && message.id && editingId !== message.id" class="msg-action-btn" title="编辑" @click="$emit('edit', message.id, message.content)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14"><path d="M11.5 2.5a1.5 1.5 0 012 2L5 13l-3 1 1-3 8.5-8.5z"/><path d="M9.5 4.5l2 2"/></svg>
          </button>
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'

interface UsageInfo {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  work_duration_sec?: number
  work_duration_ms?: number
}
interface MsgItem {
  id: number
  role: string
  content: string
  created_at?: string | null
  thinking?: string
  tool_events?: unknown[]
  usage?: UsageInfo | null
}
	
const props = defineProps<{ message: MsgItem; editingId?: number | null }>()
const emit = defineEmits<{ edit: [messageId: number, content: string]; submitEdit: [messageId: number, content: string] }>()

const isEditing = computed(() => props.message.role === 'user' && props.message.id === props.editingId && !!props.editingId)
const editText = ref('')
const editTextarea = ref<HTMLTextAreaElement | null>(null)

watch(isEditing, (v) => {
  if (v) {
    editText.value = props.message.content
    nextTick(() => {
      editTextarea.value?.focus()
      editTextarea.value?.select()
    })
  }
})

function onDocumentClick(e: MouseEvent) {
  if (isEditing.value) {
    const el = (e.target as HTMLElement)?.closest('.msg-edit-area, .msg-action-btn')
    if (!el) cancelEdit()
  }
}
onMounted(() => document.addEventListener('click', onDocumentClick))
onUnmounted(() => document.removeEventListener('click', onDocumentClick))

function submitEdit() {
  const trimmed = editText.value.trim()
  if (!trimmed) return
  emit('submitEdit', props.message.id, trimmed)
}

function cancelEdit() {
  emit('edit', 0, '')
}

function copyContent() {
  const text = props.message.content
  navigator.clipboard.writeText(text).catch(() => {
    const ta = document.createElement('textarea')
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.select(); document.execCommand('copy')
    document.body.removeChild(ta)
  })
}

const showThinking = ref(false)
const showTools = ref(false)

/** 去掉换行符，压缩连续空格，与 ThinkingCard 保持一致 */
const normalizedThinking = computed(() => {
  if (!props.message.thinking) return ''
  return props.message.thinking.replace(/[\n\r]+/g, '').replace(/[ \t]{2,}/g, ' ').trim()
})

function formatToolResult(r: unknown): string {
  if (typeof r === 'string') return r
  try { return JSON.stringify(r, null, 2) } catch { return String(r) }
}

// Configure marked to use highlight.js for code blocks
const renderer = new marked.Renderer()
renderer.code = ({ text, lang }) => {
  const language = lang || ''
  let highlighted = text
  if (language && hljs.getLanguage(language)) {
    try {
      highlighted = hljs.highlight(text, { language }).value
    } catch { /* fallback */ }
  } else if (!language) {
    try { highlighted = hljs.highlightAuto(text).value } catch { /* fallback */ }
  }
  const langLabel = language ? `<span class="code-lang">${language}</span>` : ''
  return `<div class="code-block-wrapper">
    ${langLabel}
    <button class="code-copy-btn" onclick="(function(btn){var code=btn.parentElement.querySelector('code').textContent;navigator.clipboard.writeText(code);btn.textContent='已复制';setTimeout(function(){btn.textContent='复制'},1500)})(this)">复制</button>
    <pre><code class="hljs${language ? ' language-'+language : ''}">${highlighted}</code></pre>
  </div>`
}

marked.setOptions({
  renderer,
  breaks: true,
  gfm: true,
})

const renderedContent = computed(() => {
  if (!props.message.content) return ''
  try {
    const raw = marked.parse(props.message.content, { async: false }) as string
    // 保留 target="_blank" 和 rel 属性，避免壳拦截
    return DOMPurify.sanitize(raw, { ADD_ATTR: ['target', 'rel'] })
  } catch {
    return props.message.content.replace(/</g, '&lt;').replace(/>/g, '&gt;')
  }
})

function onMsgMdClick(e: MouseEvent) {
  const a = (e.target as HTMLElement)?.closest('a')
  if (!a || !a.href || a.href.startsWith('#')) return
  e.preventDefault()
  window.open(a.href, '_blank')
}

function formatTime(iso?: string | null): string {
  if (!iso) return ''
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  } catch { return '' }
}
</script>

<style scoped>
.msg-row {
  flex-shrink: 0;
  display: flex;
  gap: var(--ag-space-md);
  margin-bottom: var(--ag-space-xl);
  animation: msgSlideUp 0.25s ease-out;
  max-width: 85%;
}
.msg-row.user { flex-direction: row-reverse; align-self: flex-end; }
.msg-row.assistant { flex-direction: row; align-self: flex-start; }

@keyframes msgSlideUp {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Avatar */
.msg-avatar {
  flex-shrink: 0;
  width: 32px; height: 32px;
  border-radius: var(--ag-radius-full);
  display: flex; align-items: center; justify-content: center;
  margin-top: 2px;
}
.msg-avatar.user { background: var(--ag-bg-user-msg); color: var(--ag-text-white); }
.msg-avatar.assistant { background: var(--ag-primary-light); color: var(--ag-primary); }

/* Card */
.msg-card { display: flex; flex-direction: column; gap: var(--ag-space-xs); min-width: 0; }
.msg-row.user .msg-card { align-items: flex-end; }
.msg-row.assistant .msg-card { align-items: flex-start; }

/* Bubble */
.msg-bubble {
  padding: var(--ag-space-md) var(--ag-space-lg);
  line-height: var(--ag-line-height-relaxed);
  font-size: var(--ag-font-size-md);
  word-break: break-word;
  overflow-wrap: break-word;
}
.msg-bubble.user {
  background: var(--ag-bg-user-msg);
  color: var(--ag-text-white);
  border-radius: var(--ag-radius-xl) var(--ag-radius-sm) var(--ag-radius-xl) var(--ag-radius-xl);
}
.msg-bubble.assistant {
  background: var(--ag-bg-assistant-msg);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm) var(--ag-radius-xl) var(--ag-radius-xl) var(--ag-radius-xl);
  box-shadow: var(--ag-shadow-sm);
}

/* Markdown content */
.msg-md :deep(p) { margin: 0 0 var(--ag-space-sm); }
.msg-md :deep(p:last-child) { margin-bottom: 0; }
.msg-md :deep(ul), .msg-md :deep(ol) { padding-left: 20px; margin: var(--ag-space-sm) 0; }
.msg-md :deep(li) { margin: 2px 0; }
.msg-md :deep(blockquote) {
  border-left: 3px solid var(--ag-primary);
  padding-left: var(--ag-space-md);
  margin: var(--ag-space-sm) 0;
  color: var(--ag-text-secondary);
}
.msg-md :deep(a) { color: var(--ag-text-link); text-decoration: none; }
.msg-md :deep(a:hover) { text-decoration: underline; }
.msg-md :deep(h1), .msg-md :deep(h2), .msg-md :deep(h3), .msg-md :deep(h4) {
  margin: var(--ag-space-lg) 0 var(--ag-space-sm);
  font-weight: 600; line-height: var(--ag-line-height-tight);
}
.msg-md :deep(h1) { font-size: 1.3em; }
.msg-md :deep(h2) { font-size: 1.15em; }
.msg-md :deep(h3) { font-size: 1.05em; }
.msg-md :deep(hr) { border: none; border-top: 1px solid var(--ag-border-light); margin: var(--ag-space-md) 0; }
.msg-md :deep(table) { border-collapse: collapse; margin: var(--ag-space-sm) 0; width: 100%; }
.msg-md :deep(th), .msg-md :deep(td) {
  border: 1px solid var(--ag-border-light); padding: var(--ag-space-sm) var(--ag-space-md);
  font-size: var(--ag-font-size-sm);
}
.msg-md :deep(th) { background: var(--ag-bg-page); font-weight: 600; }
.msg-md :deep(strong) { font-weight: 600; }
.msg-md :deep(em) { font-style: italic; }

/* Inline code */
.msg-md :deep(code:not(pre code)) {
  background: var(--ag-bg-page);
  padding: 1px 5px;
  border-radius: var(--ag-radius-sm);
  font-size: 0.9em;
  font-family: var(--ag-font-mono);
}
.msg-bubble.user .msg-md :deep(code:not(pre code)) { background: rgba(255,255,255,0.2); }

/* Code blocks */
.msg-md :deep(.code-block-wrapper) {
  position: relative;
  background: #1E1E2E;
  border-radius: var(--ag-radius-lg);
  margin: var(--ag-space-sm) 0;
  overflow: hidden;
}
.msg-md :deep(.code-lang) {
  position: absolute;
  top: 8px; left: 12px;
  font-size: var(--ag-font-size-xs);
  color: rgba(255,255,255,0.4);
  font-family: var(--ag-font-mono);
  text-transform: uppercase;
  pointer-events: none;
}
.msg-md :deep(.code-copy-btn) {
  position: absolute;
  top: 6px; right: 8px;
  padding: 2px 8px;
  border: 1px solid rgba(255,255,255,0.2);
  border-radius: var(--ag-radius-sm);
  background: rgba(255,255,255,0.08);
  color: rgba(255,255,255,0.6);
  font-size: var(--ag-font-size-xs);
  cursor: pointer;
  transition: all var(--ag-transition-fast);
}
.msg-md :deep(.code-copy-btn:hover) {
  background: rgba(255,255,255,0.15);
  color: rgba(255,255,255,0.9);
}
.msg-md :deep(pre) { margin: 0; padding: 0; }
.msg-md :deep(pre code) {
  display: block;
  padding: 32px var(--ag-space-lg) var(--ag-space-lg);
  overflow-x: auto;
  font-family: var(--ag-font-mono);
  font-size: var(--ag-font-size-sm);
  line-height: var(--ag-line-height-base);
  color: #CDD6F4;
}

/* User bubble overrides for markdown */
.msg-bubble.user .msg-md :deep(a) { color: rgba(255,255,255,0.85); text-decoration: underline; }
.msg-bubble.user .msg-md :deep(blockquote) { border-left-color: rgba(255,255,255,0.4); color: rgba(255,255,255,0.8); }
.msg-bubble.user .msg-md :deep(code:not(pre code)) { background: rgba(255,255,255,0.15); }
.msg-bubble.user .msg-md :deep(th) { background: rgba(255,255,255,0.1); }
.msg-bubble.user .msg-md :deep(th), .msg-bubble.user .msg-md :deep(td) { border-color: rgba(255,255,255,0.2); }

/* Plain text */
.msg-text {
  white-space: pre-wrap;
  line-height: var(--ag-line-height-relaxed);
}

/* Inline thinking (above the bubble) */
.inline-thinking {
  margin-bottom: var(--ag-space-sm);
  padding-bottom: var(--ag-space-sm);
  border-bottom: 1px solid var(--ag-border-light);
  width: 100%;
}
.inline-th-toggle {
  display: flex; align-items: center; gap: 5px;
  border: none; background: none; cursor: pointer;
  font-size: var(--ag-font-size-sm); color: var(--ag-text-tertiary);
  padding: 2px 0; transition: color var(--ag-transition-fast);
}
.inline-th-toggle:hover { color: var(--ag-text-secondary); }
.th-indicator {
  width: 6px; height: 6px; border-radius: var(--ag-radius-full);
  background: var(--ag-warning); flex-shrink: 0;
}
.inline-th-toggle svg { transition: transform var(--ag-transition-base); }
.inline-th-toggle svg.rotated { transform: rotate(90deg); }
.inline-th-body {
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-secondary);
  margin-top: var(--ag-space-xs);
  padding: var(--ag-space-sm) var(--ag-space-md);
  background: var(--ag-bg-page);
  border-radius: var(--ag-radius-md);
  white-space: pre-wrap;
  line-height: var(--ag-line-height-base);
}

/* Tool events inline */
.inline-tools {
  margin-top: var(--ag-space-xs);
}

/* Work duration */
.work-duration {
  font-size: var(--ag-font-size-sm);
  color: var(--ag-text-tertiary);
  margin-bottom: var(--ag-space-xs);
}
.inline-tools-toggle {
  display: flex; align-items: center; gap: 5px;
  border: none; background: none; cursor: pointer;
  font-size: var(--ag-font-size-sm); color: var(--ag-text-tertiary);
  padding: 2px 0; transition: color var(--ag-transition-fast);
}
.inline-tools-toggle:hover { color: var(--ag-text-secondary); }
.inline-tools-toggle svg { transition: transform var(--ag-transition-base); }
.inline-tools-toggle svg.rotated { transform: rotate(90deg); }
.tools-dot {
  width: 6px; height: 6px; border-radius: var(--ag-radius-full);
  background: var(--ag-success); flex-shrink: 0;
}
.inline-tools-body {
  margin-top: var(--ag-space-xs);
}
.inline-tools-body pre {
  white-space: pre-wrap; word-break: break-all;
  max-height: 200px; overflow: auto;
  background: var(--ag-bg-page);
  padding: var(--ag-space-sm) var(--ag-space-md);
  border-radius: var(--ag-radius-md);
  font-size: var(--ag-font-size-sm);
  font-family: var(--ag-font-mono);
  color: var(--ag-text-secondary);
}

/* Footer: time + usage + actions */
.msg-footer {
  display: flex; align-items: center; gap: var(--ag-space-sm);
  margin-top: 2px;
  font-size: var(--ag-font-size-xs);
}
.msg-time {
  color: var(--ag-text-tertiary);
}
.msg-usage {
  color: var(--ag-text-tertiary);
  opacity: 0.7;
}
.msg-actions {
  margin-left: auto;
  display: flex; gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
}
.msg-row:hover .msg-actions { opacity: 1; }
.msg-action-btn {
  border: none; background: none; cursor: pointer;
  font-size: 12px; padding: 1px 3px;
  color: var(--ag-text-tertiary);
  border-radius: var(--ag-radius-sm);
  line-height: 1;
}
.msg-action-btn:hover { color: var(--ag-primary); background: var(--ag-bg-page); }

/* Inline edit */
.msg-edit-area { width: 100%; }
.msg-edit-input {
  width: 100%; min-height: 60px; max-height: 200px;
  padding: var(--ag-space-sm) var(--ag-space-md);
  border: 1px solid var(--ag-primary);
  border-radius: var(--ag-radius-md);
  font-family: inherit; font-size: inherit;
  line-height: var(--ag-line-height-relaxed);
  resize: none;
  background: var(--ag-bg-base);
  color: var(--ag-text-primary);
  outline: none;
  box-sizing: border-box;
}
.msg-edit-input:focus { border-color: var(--ag-primary); box-shadow: 0 0 0 2px var(--ag-primary-light); }
.msg-edit-actions {
  display: flex; align-items: center; gap: 4px;
  margin-top: var(--ag-space-xs);
}
.msg-edit-ok, .msg-edit-cancel {
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-text-secondary);
  cursor: pointer;
  padding: 2px 6px;
  line-height: 1;
  font-size: var(--ag-font-size-sm);
}
.msg-edit-ok:hover { color: var(--ag-primary); border-color: var(--ag-primary); }
.msg-edit-cancel:hover { color: var(--ag-error); border-color: var(--ag-error); }
</style>
