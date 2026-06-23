<template>
  <div class="image-gen-app">
    <div class="toolbar">
      <div class="toolbar-row">
        <label class="field-label">模板</label>
        <select v-model="templateKey" class="tpl-select" @change="onTemplateChange">
          <option v-for="t in templates" :key="t.key" :value="t.key">
            {{ t.label }}
          </option>
        </select>
        <span v-if="templateAvailable === false" class="badge badge-warn">无凭据</span>
        <span v-else-if="templateAvailable === true" class="badge badge-ok">就绪</span>
      </div>
      <div class="toolbar-row">
        <label class="field-label">提示词</label>
        <textarea
          v-model="prompt"
          class="prompt-input"
          placeholder="描述想要生成的图片内容，如：护肤品精华液电商主图，磨砂玻璃瓶，清新蓝底"
          rows="3"
        />
      </div>
      <div class="toolbar-row">
        <label class="field-label">尺寸</label>
        <div class="size-group">
          <button
            v-for="s in sizeOptions"
            :key="s.key"
            :class="['size-btn', { active: aspectRatio === s.key }]"
            @click="aspectRatio = s.key"
          >
            {{ s.label }}
          </button>
        </div>
      </div>
      <div class="toolbar-row">
        <label class="field-label">数量</label>
        <div class="num-control">
          <button class="num-btn" :disabled="count <= 1" @click="count = Math.max(1, count - 1)">−</button>
          <span class="num-value">{{ count }}</span>
          <button class="num-btn" :disabled="count >= 4" @click="count = Math.min(4, count + 1)">+</button>
        </div>
        <button class="gen-btn" :disabled="!prompt.trim() || generating" @click="doGenerate">
          {{ generating ? '生成中…' : '生成图片' }}
        </button>
      </div>
    </div>

    <div v-if="errorMsg" class="error-bar">{{ errorMsg }}</div>

    <div v-if="generating" class="progress-hint">正在生成图片，请稍候…</div>

    <div v-if="results.length" class="results-grid">
      <div v-for="img in results" :key="img.file_id" class="result-card">
        <img :src="imageUrls[img.file_id] || ''" :alt="img.name" class="result-img" />
        <div class="result-meta">
          <span v-if="img.placeholder" class="badge badge-warn">占位图</span>
          <span class="file-size">{{ (img.size / 1024).toFixed(1) }} KB</span>
        </div>
      </div>
    </div>

    <div v-if="costInfo" class="cost-bar">
      积分消耗: {{ costInfo.points_cost ?? '—' }} | 余额: {{ costInfo.balance ?? '—' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'

interface TemplateItem {
  key: string
  label: string
  provider: string
  available: boolean
}

interface ImageResult {
  type: string
  file_id: number
  name: string
  size: number
  placeholder: boolean
  explanation?: string
}

interface GenerateResponse {
  images: ImageResult[]
  placeholder: boolean
  template: string
  points_cost?: number
  balance?: number
  error?: string
  detail?: string
}

const templates = ref<TemplateItem[]>([])
const templateKey = ref('')
const templateAvailable = ref<boolean | null>(null)
const prompt = ref('')
const aspectRatio = ref('square')
const count = ref(1)
const generating = ref(false)
const results = ref<ImageResult[]>([])
const imageUrls = ref<Record<number, string>>({})
const errorMsg = ref('')
const costInfo = ref<{ points_cost?: number; balance?: number } | null>(null)

const sizeOptions = [
  { key: 'square', label: '1:1' },
  { key: 'portrait', label: '3:4' },
  { key: 'landscape', label: '16:9' },
]

async function apiGet<T>(url: string): Promise<T> {
  const resp = await fetch(url)
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const json = await resp.json()
  if (json.success === false) throw new Error(json.error?.message || json.error || 'API error')
  return json.data as T
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const resp = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
  const json = await resp.json()
  if (json.success === false) throw new Error(json.error?.message || json.error || 'API error')
  return json.data as T
}

async function downloadImageBlob(fileId: number): Promise<Blob> {
  const token = localStorage.getItem('v2_auth_token')
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(`/api/files/download/${fileId}`, { headers })
  if (!resp.ok) throw new Error(`Download failed: ${resp.status}`)
  return resp.blob()
}

async function loadTemplates() {
  try {
    const data = await apiGet<{ templates: TemplateItem[] }>('/api/image-gen/templates')
    templates.value = data.templates
    if (data.templates.length) {
      templateKey.value = data.templates[0].key
      updateAvailable()
    }
  } catch (e: any) {
    console.warn('Failed to load templates:', e)
  }
}

function updateAvailable() {
  const t = templates.value.find(x => x.key === templateKey.value)
  templateAvailable.value = t ? t.available : null
}

function onTemplateChange() {
  updateAvailable()
}

async function doGenerate() {
  if (!prompt.value.trim() || generating.value) return
  generating.value = true
  errorMsg.value = ''
  results.value = []
  costInfo.value = null

  try {
    const data = await apiPost<GenerateResponse>('/api/image-gen/generate', {
      prompt: prompt.value,
      aspect_ratio: aspectRatio.value,
      count: count.value,
      template: templateKey.value,
      steps: 30,
    })
    if (data.error) {
      errorMsg.value = data.error
    }
    results.value = data.images || []
    imageUrls.value = {}
    for (const img of results.value) {
      try {
        const blob = await downloadImageBlob(img.file_id)
        imageUrls.value[img.file_id] = URL.createObjectURL(blob)
      } catch (e) {
        console.warn('Failed to load image', img.file_id, e)
      }
    }
    if (data.points_cost != null || data.balance != null) {
      costInfo.value = { points_cost: data.points_cost, balance: data.balance }
    }
  } catch (e: any) {
    errorMsg.value = e.message || '生成失败'
  } finally {
    generating.value = false
  }
}

onMounted(() => {
  loadTemplates()
})

onBeforeUnmount(() => {
  for (const url of Object.values(imageUrls.value)) {
    URL.revokeObjectURL(url)
  }
})
</script>

<style scoped>
.image-gen-app {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  background: var(--bg-page, #f5f6f8);
  font-family: "苹方","微软雅黑","宋体",sans-serif;
  font-size: 14px;
  color: #333;
  overflow-y: auto;
}

.toolbar {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  margin-bottom: 12px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.toolbar-row:last-child {
  margin-bottom: 0;
}

.field-label {
  min-width: 48px;
  font-weight: 500;
  color: #555;
  font-size: 13px;
}

.tpl-select {
  padding: 6px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 13px;
  background: #fff;
  min-width: 220px;
}

.prompt-input {
  flex: 1;
  padding: 8px 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 13px;
  resize: vertical;
  font-family: inherit;
  line-height: 1.5;
}

.size-group {
  display: flex;
  gap: 4px;
}

.size-btn {
  padding: 5px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  color: #555;
}
.size-btn.active {
  background: #2395bc;
  color: #fff;
  border-color: #2395bc;
}

.num-control {
  display: flex;
  align-items: center;
  gap: 6px;
}

.num-btn {
  width: 28px;
  height: 28px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fff;
  font-size: 16px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #555;
}
.num-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.num-value {
  min-width: 20px;
  text-align: center;
  font-weight: 600;
}

.gen-btn {
  margin-left: auto;
  padding: 7px 22px;
  background: #2395bc;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 14px;
  cursor: pointer;
  font-weight: 500;
}
.gen-btn:disabled {
  opacity: 0.5;
  cursor: default;
}

.badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
  font-weight: 500;
}
.badge-ok {
  background: #e6f7e6;
  color: #389e0d;
}
.badge-warn {
  background: #fff7e6;
  color: #d48806;
}

.error-bar {
  background: #fff1f0;
  color: #cf1322;
  padding: 10px 14px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 13px;
}

.progress-hint {
  text-align: center;
  padding: 24px;
  color: #888;
  font-size: 14px;
}

.results-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.result-card {
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}

.result-img {
  width: 100%;
  display: block;
  aspect-ratio: 1;
  object-fit: cover;
}

.result-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  font-size: 12px;
  color: #888;
}

.file-size {
  color: #aaa;
}

.cost-bar {
  background: #f0f5ff;
  color: #1d39c4;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}
</style>
