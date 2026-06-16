<template>
  <div class="ai-assistant">
    <div class="sidebar">
      <div class="sidebar-header">
        <h3 class="sidebar-title">Chats</h3>
        <button class="new-chat-btn" :disabled="creating" @click="newSession">
          <svg width="14" height="14" viewBox="0 0 14 14"><line x1="7" y1="1" x2="7" y2="13" stroke="currentColor" stroke-width="2"/><line x1="1" y1="7" x2="13" y2="7" stroke="currentColor" stroke-width="2"/></svg>
        </button>
      </div>
      <div v-if="loadingSessions" class="sidebar-loading">Loading...</div>
      <div v-else class="session-list">
        <div v-for="s in sessions" :key="s.id" class="session-item" :class="{ active: currentSessionId === s.id }" @click="switchSession(s)">
          <div class="session-title">{{ s.title }}</div>
          <button class="session-delete" @click.stop="deleteSession(s.id)" title="Delete">×</button>
        </div>
      </div>
    </div>

    <div class="chat-area">
      <template v-if="currentSessionId">
        <div class="messages" ref="messagesRef">
          <div v-for="msg in messages" :key="msg.id" class="message" :class="msg.role">
            <div class="avatar">{{ msg.role === 'user' ? 'You' : 'AI' }}</div>
            <div class="bubble"><div v-html="renderContent(msg.content)"></div></div>
            <div class="time">{{ formatTime(msg.createdAt) }}</div>
          </div>
          <div v-if="streaming" class="message assistant streaming-msg">
            <div class="avatar">AI</div>
            <div class="bubble"><div v-html="renderContent(streamContent)"></div><span class="cursor">|</span></div>
          </div>
          <div v-if="messages.length === 0 && !loadingMessages && !streaming" class="empty-state">
            <div class="empty-icon">🤖</div>
            <h3>Hello! How can I help you?</h3>
            <p>Ask questions, write documents, search information</p>
          </div>
        </div>

        <div class="input-area">
          <div class="input-row">
            <textarea v-model="inputText" class="input-box" placeholder="Type a message..." rows="2" @keydown.enter.exact.prevent="sendMessage" :disabled="sending"></textarea>
            <button class="send-btn" :disabled="sending || !inputText.trim()" @click="sendMessage">
              <svg v-if="!sending" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg>
              <svg v-else width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="6" width="4" height="12"/><rect x="14" y="6" width="4" height="12"/></svg>
            </button>
          </div>
        </div>
      </template>
      <div v-else class="no-session">
        <div class="empty-icon">🤖</div>
        <h3>Select a chat to start</h3>
        <p>Choose from the sidebar or create a new one</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick } from 'vue'
import api from '@/shared/api/index'

const TOKEN_KEY = 'v2_auth_token'
function headers() {
  const t = localStorage.getItem(TOKEN_KEY)
  return t ? { Authorization: `Bearer ${t}` } : {}
}

const sessions = ref<any[]>([])
const messages = ref<any[]>([])
const currentSessionId = ref<number | null>(null)
const loadingSessions = ref(false)
const loadingMessages = ref(false)
const creating = ref(false)
const sending = ref(false)
const streaming = ref(false)
const streamContent = ref('')
const inputText = ref('')
const messagesRef = ref<HTMLElement | null>(null)

function formatTime(t: string) {
  if (!t) return ''
  const d = new Date(t)
  return `${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`
}

function renderContent(c: string) {
  if (!c) return ''
  return c.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/\n/g, '<br>')
         .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/\*(.+?)\*/g, '<em>$1</em>')
}

function scroll() { nextTick(() => messagesRef.value?.scrollTo({ top: messagesRef.value.scrollHeight })) }

async function loadSessions() {
  loadingSessions.value = true
  try {
    const res = await api.get('/agent/sessions', { headers: headers() })
    if (res.data?.success && res?.data?.data?.items) sessions.value = res.data.data.items
  } catch { /* ignore */ }
  finally { loadingSessions.value = false }
}

async function loadMessages(sid: number) {
  loadingMessages.value = true
  messages.value = []
  try {
    const res = await api.get(`/agent/sessions/${sid}/messages`, { headers: headers() })
    if (res.data?.success && res?.data?.data?.items) messages.value = res.data.data.items
  } catch { /* ignore */ }
  finally { loadingMessages.value = false; scroll() }
}

async function newSession() {
  creating.value = true
  try {
    const res = await api.post('/agent/sessions', { title: 'New Chat' }, { headers: headers() })
    if (res.data?.success && res.data.data) {
      sessions.value.unshift(res.data.data)
      currentSessionId.value = res.data.data.id
      messages.value = []
    }
  } catch { /* ignore */ }
  finally { creating.value = false }
}

async function switchSession(s: any) {
  currentSessionId.value = s.id
  await loadMessages(s.id)
}

async function deleteSession(id: number) {
  try {
    await api.delete(`/agent/sessions/${id}`, { headers: headers() })
  } catch { /* ignore */ }
  sessions.value = sessions.value.filter((s: any) => s.id !== id)
  if (currentSessionId.value === id) {
    currentSessionId.value = sessions.value[0]?.id || null
    if (currentSessionId.value) await loadMessages(currentSessionId.value)
    else messages.value = []
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || sending.value || !currentSessionId.value) return
  inputText.value = ''
  sending.value = true
  streaming.value = true
  streamContent.value = ''
  messages.value.push({ id: Date.now(), role: 'user', content: text, createdAt: new Date().toISOString() })
  scroll()

  try {
    const res = await api.post(`/agent/sessions/${currentSessionId.value}/message`, { content: text, model: 'deepseek-v4-flash' }, { headers: headers(), timeout: 60000 })
    const data = res?.data || res
    const content = data?.content || (typeof data === 'string' ? data : '')
    if (content) {
      streamContent.value = content
      await new Promise(r => setTimeout(r, 100))
      messages.value.push({ id: Date.now() + 1, role: 'assistant', content, createdAt: new Date().toISOString() })
      streamContent.value = ''
    }
  } catch {
    messages.value.push({ id: Date.now() + 1, role: 'assistant', content: 'Sorry, an error occurred. Please try again.', createdAt: new Date().toISOString() })
  } finally {
    sending.value = false
    streaming.value = false
    scroll()
  }
}

onMounted(() => loadSessions())
</script>

<style scoped>
.ai-assistant { display: flex; height: 100%; background: #f8fafc; }
.sidebar { width: 220px; background: #fff; border-right: 1px solid #e2e8f0; display: flex; flex-direction: column; flex-shrink: 0; }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 12px; border-bottom: 1px solid #e2e8f0; }
.sidebar-title { font-size: 14px; font-weight: 600; margin: 0; color: #1e293b; }
.new-chat-btn { width: 24px; height: 24px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; color: #64748b; }
.new-chat-btn:hover { background: #6366f1; color: #fff; border-color: #6366f1; }
.new-chat-btn:disabled { opacity: .4; cursor: not-allowed; }
.sidebar-loading { padding: 20px; text-align: center; color: #94a3b8; font-size: 12px; }
.session-list { flex: 1; overflow-y: auto; padding: 4px; }
.session-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; margin: 2px 0; border-radius: 6px; cursor: pointer; }
.session-item:hover { background: #f1f5f9; }
.session-item.active { background: #eef2ff; }
.session-title { font-size: 12px; color: #334155; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.session-delete { width: 16px; height: 16px; border: none; background: none; cursor: pointer; color: #94a3b8; font-size: 14px; display: none; padding: 0; line-height: 1; }
.session-item:hover .session-delete { display: block; }
.session-delete:hover { color: #ef4444; }
.chat-area { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.messages { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 8px; }
.message { display: flex; gap: 10px; max-width: 720px; width: 100%; margin: 0 auto; }
.message.user { flex-direction: row-reverse; }
.avatar { width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 700; flex-shrink: 0; margin-top: 2px; }
.message.assistant .avatar { background: linear-gradient(135deg,#6366f1,#8b5cf6); color: #fff; }
.message.user .avatar { background: linear-gradient(135deg,#10b981,#059669); color: #fff; }
.bubble { background: #fff; border-radius: 12px; padding: 10px 14px; box-shadow: 0 2px 8px rgba(15,23,42,.06); border: 1px solid rgba(148,163,184,.12); font-size: 13px; line-height: 1.6; word-break: break-word; max-width: 85%; }
.message.user .bubble { background: #6366f1; color: #fff; border-color: transparent; }
.time { font-size: 10px; color: #94a3b8; align-self: flex-end; padding: 0 4px; }
.cursor { display: inline-block; animation: blink .8s infinite; color: #6366f1; font-weight: 700; margin-left: 2px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
.empty-state, .no-session { display: flex; flex-direction: column; align-items: center; justify-content: center; flex: 1; padding: 60px 20px; text-align: center; }
.empty-icon { width: 56px; height: 56px; border-radius: 50%; background: linear-gradient(135deg,rgba(99,102,241,.1),rgba(139,92,246,.05)); display: flex; align-items: center; justify-content: center; font-size: 26px; margin-bottom: 12px; }
.empty-state h3, .no-session h3 { font-size: 15px; font-weight: 600; color: #1e293b; margin: 0 0 4px; }
.empty-state p, .no-session p { font-size: 12px; color: #64748b; margin: 0; }
.input-area { padding: 12px 20px 16px; border-top: 1px solid #e2e8f0; background: #fff; }
.input-row { display: flex; gap: 8px; align-items: flex-end; }
.input-box { flex: 1; padding: 8px 12px; border: 1px solid #e2e8f0; border-radius: 8px; font-size: 13px; line-height: 1.5; resize: none; outline: none; font-family: inherit; }
.input-box:focus { border-color: #6366f1; }
.send-btn { width: 34px; height: 34px; border: none; border-radius: 8px; background: #6366f1; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.send-btn:hover { background: #4f46e5; }
.send-btn:disabled { background: #cbd5e1; cursor: not-allowed; }
</style>
