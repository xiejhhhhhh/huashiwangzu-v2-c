<template>
  <section class="im-app">
    <div class="im-sidebar">
      <div class="im-sidebar-header">
        <span class="im-sidebar-title">会话</span>
        <button class="im-new-chat-btn" @click="showUserPicker = true" title="发起新对话">+</button>
      </div>
      <div class="im-conv-list">
        <div v-for="conv in conversations" :key="conv.id"
          class="im-conv-item"
          :class="{ 'im-conv-item-active': activeConvId === conv.id }"
          @click="selectConversation(conv.id)">
          <div class="im-conv-avatar">{{ getConvAvatar(conv) }}</div>
          <div class="im-conv-info">
            <div class="im-conv-top">
              <span class="im-conv-name">{{ getConvName(conv) }}</span>
              <span v-if="conv.unread_count > 0" class="im-conv-badge">{{ conv.unread_count > 99 ? '99+' : conv.unread_count }}</span>
            </div>
            <div class="im-conv-last">{{ conv.last_message_summary || '暂无消息' }}</div>
          </div>
        </div>
        <div v-if="!conversations.length" class="im-conv-empty">暂无会话</div>
      </div>
    </div>
    <div class="im-main">
      <template v-if="activeConvId">
        <div class="im-messages" ref="messagesRef">
          <div v-for="msg in messages" :key="msg.id" class="im-msg"
            :class="{ 'im-msg-self': msg.sender_id === currentUserId, 'im-msg-notification': msg.msg_type === 'notification' }">
            <div class="im-msg-sender">{{ msg.msg_type === 'notification' ? '系统通知' : (msg.sender_id === currentUserId ? '我' : getSenderName(msg.sender_id)) }}</div>
            <div class="im-msg-bubble">{{ msg.content }}</div>
            <div class="im-msg-time">{{ formatTime(msg.created_at) }}</div>
          </div>
          <div v-if="loadingMessages" class="im-loading">加载中...</div>
        </div>
        <div class="im-input-area">
          <textarea v-model="inputText" class="im-input" placeholder="输入消息..." @keydown.enter.prevent="sendMessage" rows="3"></textarea>
          <div class="im-input-actions">
            <span class="im-input-hint">Enter 发送</span>
            <button class="im-send-btn" @click="sendMessage" :disabled="!inputText.trim() || sending">发送</button>
          </div>
        </div>
      </template>
      <div v-else class="im-no-conv">选择左侧会话开始聊天</div>
    </div>

    <div v-if="showUserPicker" class="im-user-picker-overlay" @click.self="showUserPicker = false">
      <div class="im-user-picker">
        <div class="im-user-picker-header">选择联系人</div>
        <div class="im-user-picker-list">
          <div v-for="u in availableUsers" :key="u.id" class="im-user-item" @click="startChat(u.id)">
            <div class="im-user-avatar">{{ (u.display_name || u.username)[0] }}</div>
            <span>{{ u.display_name || u.username }}</span>
          </div>
          <div v-if="!availableUsers.length" class="im-loading">加载中...</div>
        </div>
        <button class="im-user-picker-close" @click="showUserPicker = false">取消</button>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, nextTick, watch } from 'vue'
import { initRuntime, getApiUrl, platform, authHeaders, apiGet, apiPost } from '../runtime'

interface Conversation {
  id: number; conv_type: string; creator_id: number; member_ids: number[]
  last_message_summary: string; last_message_at: string | null; unread_count: number; updated_at: string | null
}
interface Message {
  id: number; conversation_id: number; sender_id: number; content: string; msg_type: string; created_at: string
}
interface UserInfo {
  id: number; username: string; display_name: string
}

const conversations = ref<Conversation[]>([])
const messages = ref<Message[]>([])
const activeConvId = ref<number | null>(null)
const inputText = ref('')
const showUserPicker = ref(false)
const availableUsers = ref<UserInfo[]>([])
const loadingMessages = ref(false)
const sending = ref(false)
const currentUserId = ref(0)
const messagesRef = ref<HTMLElement | null>(null)

let pollTimer: ReturnType<typeof setInterval> | null = null
let msgPollTimer: ReturnType<typeof setInterval> | null = null
let lastMsgId = ref(0)

async function loadConversations() {
  try {
    conversations.value = await apiGet<Conversation[]>('/im/conversations')
  } catch (e) {
    console.error('Failed to load conversations', e)
  }
}

async function loadMessages(convId: number) {
  loadingMessages.value = true
  try {
    const msgs = await apiGet<Message[]>(`/im/conversations/${convId}/messages?page=1&page_size=100`)
    messages.value = msgs
    if (msgs.length > 0) {
      lastMsgId.value = msgs[msgs.length - 1].id
    }
    await nextTick()
    scrollToBottom()
  } catch (e) {
    console.error('Failed to load messages', e)
  } finally {
    loadingMessages.value = false
  }
}

async function pollMessages(convId: number) {
  try {
    const msgs = await apiGet<Message[]>(`/im/conversations/${convId}/messages?page=1&page_size=50`)
    if (msgs.length > 0 && msgs[msgs.length - 1].id > lastMsgId.value) {
      const newMsgs = msgs.filter(m => m.id > lastMsgId.value)
      messages.value = messages.value.concat(newMsgs)
      lastMsgId.value = msgs[msgs.length - 1].id
      await nextTick()
      scrollToBottom()
    }
  } catch (e) {
    console.error('Failed to poll messages', e)
  }
}

async function selectConversation(convId: number) {
  activeConvId.value = convId
  await loadMessages(convId)

  try {
    const msgs = messages.value
    if (msgs.length > 0) {
      const lastId = msgs[msgs.length - 1].id
      await apiPost(`/im/conversations/${convId}/read`, { last_read_message_id: lastId })
    }
    loadConversations()
  } catch (e) {
    console.error('Failed to mark read', e)
  }
}

async function sendMessage() {
  const text = inputText.value.trim()
  if (!text || !activeConvId.value || sending.value) return
  sending.value = true
  try {
    await apiPost('/im/messages', {
      conversation_id: activeConvId.value,
      content: text,
    })
    inputText.value = ''
    await loadMessages(activeConvId.value)
    loadConversations()
  } catch (e) {
    console.error('Failed to send message', e)
  } finally {
    sending.value = false
  }
}

async function loadUsers() {
  try {
    availableUsers.value = await apiGet<UserInfo[]>('/im/users')
  } catch (e) {
    console.error('Failed to load users', e)
  }
}

async function startChat(targetUserId: number) {
  showUserPicker.value = false
  try {
    const result = await apiPost<{ conversation_id: number }>('/im/messages', {
      target_user_id: targetUserId,
      content: '',
    })
    if (result && result.conversation_id) {
      activeConvId.value = result.conversation_id
      await loadMessages(result.conversation_id)
    }
    loadConversations()
  } catch {
    try {
      await apiPost('/im/messages', {
        target_user_id: targetUserId,
        content: '你好',
      })
      loadConversations()
    } catch (e) {
      console.error('Failed to start chat', e)
    }
  }
}

function getConvAvatar(conv: Conversation): string {
  if (conv.conv_type === 'single') {
    const otherId = conv.member_ids.find(id => id !== currentUserId.value)
    const otherUser = availableUsers.value.find(u => u.id === otherId)
    return (otherUser?.display_name || otherUser?.username || '?')[0]
  }
  return 'G'
}

function getConvName(conv: Conversation): string {
  if (conv.conv_type === 'single') {
    const otherId = conv.member_ids.find(id => id !== currentUserId.value)
    const otherUser = availableUsers.value.find(u => u.id === otherId)
    return otherUser?.display_name || otherUser?.username || `用户${otherId}`
  }
  return `群聊(${conv.member_ids.length}人)`
}

function getSenderName(senderId: number): string {
  if (senderId === 0) return '系统'
  const user = availableUsers.value.find(u => u.id === senderId)
  return user?.display_name || user?.username || `用户${senderId}`
}

function formatTime(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function scrollToBottom() {
  if (messagesRef.value) {
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight
  }
}

onMounted(async () => {
  await initRuntime('im')
  try {
    const user = await platform.auth.getCurrentUser()
    currentUserId.value = user.id
  } catch {
    console.warn('Cannot get current user')
  }
  await loadUsers()
  await loadConversations()
  pollTimer = setInterval(loadConversations, 5000)
})

watch(activeConvId, (newVal) => {
  if (msgPollTimer) {
    clearInterval(msgPollTimer)
    msgPollTimer = null
  }
  if (newVal) {
    msgPollTimer = setInterval(() => pollMessages(newVal), 3000)
  }
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (msgPollTimer) clearInterval(msgPollTimer)
})
</script>

<style scoped>
.im-app {
  display: flex; height: 100%; background: #fff; border-radius: 0; overflow: hidden;
  font-family: 苹方, "微软雅黑", 宋体, sans-serif;
  color: #333;
}
.im-sidebar {
  width: 280px; min-width: 280px; border-right: 1px solid #e8e8e8;
  display: flex; flex-direction: column; background: #f8f9fa;
}
.im-sidebar-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px; border-bottom: 1px solid #e8e8e8;
}
.im-sidebar-title { font-size: 16px; font-weight: 600; color: #2395bc; }
.im-new-chat-btn {
  width: 32px; height: 32px; border: none; border-radius: 8px;
  background: #2395bc; color: #fff; font-size: 20px; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .15s;
}
.im-new-chat-btn:hover { background: #31A1C6; }
.im-conv-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.im-conv-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 16px; cursor: pointer; transition: background .12s;
  border-left: 3px solid transparent;
}
.im-conv-item:hover { background: #eef2f5; }
.im-conv-item-active { background: #e3f0f7; border-left-color: #2395bc; }
.im-conv-avatar {
  width: 40px; height: 40px; border-radius: 50%;
  background: #2395bc; color: #fff; display: flex; align-items: center;
  justify-content: center; font-size: 16px; font-weight: 600;
  flex-shrink: 0;
}
.im-conv-info { flex: 1; min-width: 0; }
.im-conv-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.im-conv-name { font-size: 14px; font-weight: 500; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-conv-badge {
  font-size: 11px; color: #fff; background: #f56c6c; border-radius: 10px;
  padding: 0 6px; min-width: 18px; height: 18px; line-height: 18px;
  text-align: center; font-weight: 600; flex-shrink: 0;
}
.im-conv-last { font-size: 12px; color: #999; margin-top: 3px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.im-conv-empty { text-align: center; color: #ccc; padding: 40px 16px; font-size: 14px; }
.im-main { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.im-messages { flex: 1; overflow-y: auto; padding: 16px 20px; }
.im-msg { margin-bottom: 16px; max-width: 70%; }
.im-msg-self { margin-left: auto; }
.im-msg-self .im-msg-bubble { background: #2395bc; color: #fff; border-radius: 12px 12px 4px 12px; }
.im-msg-notification { max-width: 90%; margin-left: auto; margin-right: auto; }
.im-msg-notification .im-msg-bubble { background: #fef6e7; color: #b8860b; border: 1px solid #f0d88a; border-radius: 8px; text-align: center; font-size: 13px; }
.im-msg-sender { font-size: 11px; color: #aaa; margin-bottom: 4px; }
.im-msg-self .im-msg-sender { text-align: right; }
.im-msg-bubble { background: #f0f0f0; padding: 10px 14px; border-radius: 12px 12px 12px 4px; font-size: 14px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; }
.im-msg-time { font-size: 10px; color: #ccc; margin-top: 4px; }
.im-msg-self .im-msg-time { text-align: right; }
.im-input-area { border-top: 1px solid #e8e8e8; padding: 12px 16px; background: #fafafa; }
.im-input { width: 100%; border: 1px solid #ddd; border-radius: 8px; padding: 10px 12px; font-size: 14px; resize: none; outline: none; font-family: inherit; box-sizing: border-box; transition: border .15s; }
.im-input:focus { border-color: #2395bc; }
.im-input-actions { display: flex; align-items: center; justify-content: space-between; margin-top: 8px; }
.im-input-hint { font-size: 12px; color: #bbb; }
.im-send-btn { background: #2395bc; color: #fff; border: none; border-radius: 6px; padding: 8px 20px; font-size: 14px; cursor: pointer; transition: background .15s; }
.im-send-btn:hover { background: #31A1C6; }
.im-send-btn:disabled { background: #b0d4e3; cursor: not-allowed; }
.im-no-conv { display: flex; align-items: center; justify-content: center; height: 100%; color: #ccc; font-size: 16px; }
.im-loading { text-align: center; color: #ccc; padding: 20px; font-size: 14px; }

.im-user-picker-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.3);
  display: flex; align-items: center; justify-content: center; z-index: 9999;
}
.im-user-picker { background: #fff; border-radius: 12px; width: 380px; max-height: 500px; display: flex; flex-direction: column; box-shadow: 0 8px 30px rgba(0,0,0,.15); }
.im-user-picker-header { padding: 16px 20px; font-size: 16px; font-weight: 600; color: #2395bc; border-bottom: 1px solid #e8e8e8; }
.im-user-picker-list { flex: 1; overflow-y: auto; padding: 8px 0; }
.im-user-item {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 20px; cursor: pointer; transition: background .12s;
}
.im-user-item:hover { background: #eef2f5; }
.im-user-avatar {
  width: 36px; height: 36px; border-radius: 50%;
  background: #31A1C6; color: #fff; display: flex; align-items: center;
  justify-content: center; font-size: 14px; font-weight: 600;
}
.im-user-picker-close { margin: 12px 16px; padding: 8px; border: 1px solid #ddd; border-radius: 6px; background: #fff; cursor: pointer; color: #666; font-size: 14px; text-align: center; }
.im-user-picker-close:hover { background: #f5f5f5; }
</style>
