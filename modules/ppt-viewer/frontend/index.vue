<template>
  <viewer-shell
    :file-name="fileName"
    app-name="演示文稿查看器"
    file-icon="📽️"
    :show-download="true"
    @download="handleDownload"
  >
    <template #toolbar-center>
      <div class="pv-slide-nav" v-if="slides.length > 0">
        <button class="vs-btn" :disabled="currentSlide <= 0" @click="goSlide(currentSlide - 1)">上一张</button>
        <span class="pv-slide-info">{{ currentSlide + 1 }} / {{ slides.length }}</span>
        <button class="vs-btn" :disabled="currentSlide >= slides.length - 1" @click="goSlide(currentSlide + 1)">下一张</button>
      </div>
    </template>
    <div class="pt-container">
      <div v-if="loadError" class="pt-error">{{ loadError }}</div>
      <div v-else-if="loading" class="pt-loading">
        <div class="iv-spinner"></div>
        <p>解析演示文稿中...</p>
      </div>
      <div v-else class="pt-layout">
        <div class="pt-thumbnails" v-if="slides.length > 0">
          <div
            v-for="(slide, idx) in slides"
            :key="idx"
            class="pt-thumb"
            :class="{ active: currentSlide === idx }"
            @click="goSlide(idx)"
          >
            <div class="pt-thumb-num">{{ idx + 1 }}</div>
            <div class="pt-thumb-content">{{ slideTitle(slide) }}</div>
          </div>
        </div>
        <div class="pt-main">
          <div class="pt-slide" v-if="currentSlideData">
            <div v-for="(elem, ei) in currentSlideData.elements" :key="ei" class="pt-elem" :class="`pt-elem-${elem.type}`">
              <div v-if="elem.type === 'textbox'" class="pt-textbox">{{ elem.content }}</div>
              <div v-else-if="elem.type === 'image'" class="pt-image-placeholder">[图片]</div>
            </div>
          </div>
          <div v-else-if="slides.length === 0" class="pt-empty">无内容</div>
        </div>
      </div>
    </div>
    <template #statusbar>
      <span v-if="slides.length > 0">{{ slides.length }} 张幻灯片</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import viewerShell from '@/shared/components/viewer-shell.vue'
import { apiPost, downloadBlob } from './api'

const props = defineProps<{ fileId?: number; fileName?: string; format?: string; mode?: string }>()

function getPayload(): { fileId: number; fileName: string } | null {
  // 框架通过 <component v-bind="payload"> 把 fileId 作为 prop 传进来
  if (props.fileId) return { fileId: Number(props.fileId), fileName: props.fileName || '' }
  const p = (window as unknown as { __MODULE_OPEN_FILE_PAYLOAD__?: { fileId?: number; fileName?: string } }).__MODULE_OPEN_FILE_PAYLOAD__
  if (p?.fileId) return { fileId: Number(p.fileId), fileName: p.fileName || '' }
  return null
}

const fileName = ref('')
const loading = ref(true)
const loadError = ref('')
interface SlideElement {
  type: string
  content?: string
  resourceRef?: number | null
}

interface Slide {
  index: number
  elements: SlideElement[]
}

const slides = ref<Slide[]>([])
const currentSlide = ref(0)
const fileBlobUrl = ref('')

const currentSlideData = computed(() => slides.value[currentSlide.value] || null)

function slideTitle(slide: Slide): string {
  const textbox = (slide.elements || []).find((e: SlideElement) => e.type === 'textbox')
  return textbox ? textbox.content?.slice(0, 40) || '' : `幻灯片 ${slide.index + 1}`
}

interface ParseResponse {
  content?: unknown
  blocks?: unknown
  text?: unknown
  page?: unknown
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function toText(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function toPage(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : 1
}

function toResourceRef(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

function normalizeLegacySlide(raw: unknown): Slide | null {
  if (!isRecord(raw) || !Array.isArray(raw.elements)) return null
  const index = typeof raw.index === 'number' && Number.isFinite(raw.index) ? raw.index : 0
  const elements = raw.elements
    .filter(isRecord)
    .map((elem): SlideElement => ({
      type: toText(elem.type) || 'textbox',
      content: toText(elem.content),
      resourceRef: toResourceRef(elem.resource_ref),
    }))
  return { index, elements }
}

function normalizeParseResponse(data: ParseResponse): Slide[] {
  if (Array.isArray(data.content)) {
    const legacySlides = data.content
      .map(normalizeLegacySlide)
      .filter((slide): slide is Slide => slide !== null)
    if (legacySlides.length > 0) return legacySlides
  }

  const source = Array.isArray(data.blocks) ? data.blocks : []
  const grouped = new Map<number, SlideElement[]>()
  for (const raw of source) {
    if (!isRecord(raw)) continue
    const type = toText(raw.type)
    const text = toText(raw.text) || toText(raw.content)
    const page = toPage(raw.page)
    const elements = grouped.get(page) ?? []
    if (type === 'image') {
      elements.push({ type: 'image', content: text, resourceRef: toResourceRef(raw.resource_ref) })
    } else if (text.trim()) {
      elements.push({ type: 'textbox', content: text, resourceRef: null })
    }
    grouped.set(page, elements)
  }

  if (grouped.size === 0) {
    const text = toText(data.text)
    return text.trim()
      ? [{ index: toPage(data.page) - 1, elements: [{ type: 'textbox', content: text, resourceRef: null }] }]
      : []
  }

  return Array.from(grouped.entries())
    .sort(([left], [right]) => left - right)
    .map(([page, elements]) => ({ index: page - 1, elements }))
}

async function loadPpt(fid: number) {
  try {
    loadError.value = ''
    loading.value = true
    const data = await apiPost<ParseResponse>('/modules/call', {
      target_module: 'pptx-parser',
      action: 'parse',
      parameters: { file_id: fid },
    })
    slides.value = normalizeParseResponse(data)
    currentSlide.value = 0
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '演示文稿解析失败'
  } finally {
    loading.value = false
  }
}

function goSlide(idx: number) {
  if (idx < 0 || idx >= slides.value.length) return
  currentSlide.value = idx
}

function handleDownload() {
  if (!fileBlobUrl.value) return
  const a = document.createElement('a')
  a.href = fileBlobUrl.value
  a.download = fileName.value
  a.click()
}

onMounted(async () => {
  const payload = getPayload()
  if (payload && payload.fileId) {
    fileName.value = payload.fileName || 'presentation.pptx'
    try {
      const blob = await downloadBlob(payload.fileId)
      fileBlobUrl.value = URL.createObjectURL(blob)
    } catch { /* download not available */ }
    loadPpt(payload.fileId)
  }
})
</script>

<style scoped>
.pt-container {
  width: 100%;
  height: 100%;
  display: flex;
  background: #f0f0f0;
}

.pt-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 100%;
  gap: 12px;
  color: #999;
  font-size: 14px;
}

.iv-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e0e0;
  border-top-color: var(--mac-app-accent, #0a84ff);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.pt-layout {
  display: flex;
  width: 100%;
  height: 100%;
}

.pt-thumbnails {
  width: 180px;
  overflow-y: auto;
  background: #e0e0e0;
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex-shrink: 0;
}

.pt-thumb {
  padding: 8px 10px;
  background: #fff;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  border: 2px solid transparent;
  transition: all 0.15s;
}

.pt-thumb:hover {
  border-color: var(--mac-app-accent, #0a84ff)55;
}

.pt-thumb.active {
  border-color: var(--mac-app-accent, #0a84ff);
  background: #eef7fa;
}

.pt-thumb-num {
  font-weight: 600;
  color: var(--mac-app-accent, #0a84ff);
  font-size: 11px;
  margin-bottom: 4px;
}

.pt-thumb-content {
  color: #555;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pt-main {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  overflow-y: auto;
}

.pt-slide {
  background: #fff;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.12);
  width: 100%;
  max-width: 800px;
  aspect-ratio: 16 / 9;
  padding: 32px 40px;
  overflow-y: auto;
}

.pt-elem {
  margin-bottom: 12px;
}

.pt-textbox {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
}

.pt-image-placeholder {
  background: #f0f0f0;
  border: 1px dashed #ccc;
  padding: 20px;
  text-align: center;
  color: #999;
  font-size: 13px;
  border-radius: 4px;
}

.pt-empty {
  color: #999;
  font-size: 14px;
}

.pt-error {
  padding: 40px;
  text-align: center;
  color: #e74c3c;
  font-size: 14px;
  width: 100%;
}

.pv-slide-nav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pv-slide-info {
  font-size: 13px;
  color: #555;
  white-space: nowrap;
}
</style>
