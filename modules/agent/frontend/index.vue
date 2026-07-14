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
import { useAgentChat } from './composables/useAgentChat'
import type { AgentEntryProps } from './types'
import { apiPost } from './api'
import './components/style-variables.css'

// ── 全局前端错误自动上报 ─────────────────────────────────
function _setupFrontendErrorReporting(): void {
  const throttle = new Map<string, number>()
  const INTERVAL = 10_000 // ms, 同一种错误最多每 10 秒上报一次

  function report(type: string, msg: string, stack: string | undefined, url?: string) {
    const key = `${type}:${msg?.slice(0, 100)}`
    const last = throttle.get(key) || 0
    const now = Date.now()
    if (now - last < INTERVAL) return
    throttle.set(key, now)
    const page_path = window.location.pathname
    apiPost('/logs/frontend-error', { type, error_message: msg, stack: stack?.slice(0, 2000), page_path, url })
      .catch(() => {/* 静默失败，不上报错误的上报错误 */})
  }

  if (typeof window !== 'undefined') {
    window.onerror = (_event, source, _line, _col, error) => {
      report('runtime', error?.message || String(_event), error?.stack, source || undefined)
    }
    window.addEventListener('unhandledrejection', (event) => {
      const reason = event.reason
      report('promise', reason?.message || String(reason), reason?.stack)
    })
  }
}
_setupFrontendErrorReporting()
// ─────────────────────────────────────────────────────────

const props = defineProps<AgentEntryProps>()

const {
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
} = useAgentChat(props)
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
