<template>
  <viewer-shell
    :file-name="fileName"
    app-name="文本编辑器"
    file-icon="📄"
    :show-save="isEditable && content !== originalContent"
    :show-download="true"
    @save="handleSave"
    @download="handleDownload"
  >
    <template #toolbar-extra>
      <button
        v-if="isMarkdown"
        class="vs-btn"
        @click="previewMode = !previewMode"
      >
        {{ previewMode ? '源码' : '预览' }}
      </button>
    </template>
    <div class="te-container">
      <div v-if="previewMode && isMarkdown" class="te-preview" v-html="renderedMarkdown"></div>
      <textarea
        v-else
        ref="textareaRef"
        class="te-textarea"
        :value="content"
        :readonly="!isEditable"
        @input="onInput"
      ></textarea>
    </div>
    <template #statusbar>
      <span>{{ statusText }}</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import viewerShell from '@/shared/components/viewer-shell.vue'

const TOKEN_KEY = 'v2_auth_token'

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem(TOKEN_KEY)
  return token ? { Authorization: `Bearer ${token}` } : {}
}

function getPayload(): { fileId: number; fileName: string } | null {
  const p = (window as any).__MODULE_OPEN_FILE_PAYLOAD__
  if (p?.fileId) return { fileId: p.fileId, fileName: p.fileName || '' }
  return null
}

const fileName = ref('')
const content = ref('')
const originalContent = ref('')
const isEditable = ref(true)
const isMarkdown = ref(false)
const previewMode = ref(false)
const loadError = ref('')
const saveError = ref('')
const fileId = ref(0)
const format = ref('')
const textareaRef = ref<HTMLTextAreaElement | null>(null)

const renderedMarkdown = computed(() => {
  if (!isMarkdown.value) return ''
  try {
    const md = (content.value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    const html = md
      .replace(/^### (.+)$/gm, '<h3>$1</h3>')
      .replace(/^## (.+)$/gm, '<h2>$1</h2>')
      .replace(/^# (.+)$/gm, '<h1>$1</h1>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.+?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/^- (.+)$/gm, '<li>$1</li>')
      .replace(/(<li>.*<\/li>\n?)+/g, '<ul>$&</ul>')
      .replace(/\n\n/g, '</p><p>')
      .replace(/\n/g, '<br>')
    return `<p>${html}</p>`
  } catch {
    return content.value || ''
  }
})

const statusText = computed(() => {
  if (loadError.value) return loadError.value
  if (saveError.value) return saveError.value
  const len = content.value?.length || 0
  const changed = content.value !== originalContent.value
  const lines = (content.value || '').split('\n').length
  return `${lines} 行, ${len} 字符${changed ? ' (已修改)' : ''}`
})

async function loadText(fid: number) {
  try {
    loadError.value = ''
    const url = `/api/files/download/${fid}`
    const resp = await fetch(url, { headers: authHeaders() })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const text = await resp.text()
    content.value = text
    originalContent.value = text
  } catch (e: any) {
    loadError.value = e.message || '加载失败'
  }
}

function onInput(e: Event) {
  content.value = (e.target as HTMLTextAreaElement).value
}

async function handleSave() {
  if (content.value === originalContent.value) return
  saveError.value = ''
  try {
    const formData = new FormData()
    const blob = new Blob([content.value], { type: 'text/plain' })
    formData.append('file', blob, fileName.value || 'untitled.txt')
    const resp = await fetch('/api/files/upload', {
      method: 'POST',
      headers: authHeaders(),
      body: formData,
    })
    const json = await resp.json()
    if (!json.success) throw new Error(json.error || '保存失败')
    originalContent.value = content.value
  } catch (e: any) {
    saveError.value = e.message || '保存失败'
  }
}

function handleDownload() {
  const blob = new Blob([content.value], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName.value
  a.click()
  URL.revokeObjectURL(url)
}

onMounted(() => {
  const payload = getPayload()
  if (payload && payload.fileId) {
    fileId.value = payload.fileId
    fileName.value = payload.fileName || 'untitled'
    const ext = (payload.fileName || '').split('.').pop()?.toLowerCase() || ''
    format.value = ext
    isMarkdown.value = ext === 'md'
    isEditable.value = ['txt', 'md', 'log', 'json', 'yaml', 'yml', 'xml', 'ini', 'cfg'].includes(ext)
    loadText(payload.fileId)
  }
})
</script>

<style scoped>
.te-container {
  width: 100%;
  height: 100%;
  display: flex;
  background: #fff;
}

.te-textarea {
  width: 100%;
  height: 100%;
  border: none;
  outline: none;
  resize: none;
  padding: 16px;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 13px;
  line-height: 1.6;
  color: #333;
  background: #fafafa;
  tab-size: 2;
}

.te-textarea:focus {
  background: #fff;
}

.te-preview {
  width: 100%;
  height: 100%;
  padding: 16px 20px;
  overflow-y: auto;
  font-size: 14px;
  line-height: 1.7;
  color: #333;
}

.te-preview :deep(h1),
.te-preview :deep(h2),
.te-preview :deep(h3) {
  color: #2395bc;
  margin-top: 20px;
  margin-bottom: 10px;
}

.te-preview :deep(h1) { font-size: 22px; }
.te-preview :deep(h2) { font-size: 18px; }
.te-preview :deep(h3) { font-size: 15px; }

.te-preview :deep(code) {
  background: #f0f0f0;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
  font-size: 12px;
}

.te-preview :deep(ul) {
  padding-left: 20px;
}

.te-preview :deep(li) {
  list-style: disc;
}
</style>
