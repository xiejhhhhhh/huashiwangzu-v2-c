<template>
  <viewer-shell
    :file-name="fileName"
    app-name="图片查看器"
    file-icon="🖼️"
    :show-download="true"
    :show-zoom-in="true"
    :show-zoom-out="true"
    :show-fit="true"
    @download="handleDownload"
    @zoom-in="zoomIn"
    @zoom-out="zoomOut"
    @fit="fitToWindow"
  >
    <div class="iv-container">
      <div class="iv-viewport" ref="viewportRef">
        <img
          v-if="imageSrc"
          :src="imageSrc"
          class="iv-image"
          :style="imageStyle"
          :class="{ 'iv-dragging': isDragging }"
          draggable="false"
          @mousedown="startDrag"
          @mousemove="doDrag"
          @mouseup="stopDrag"
          @mouseleave="stopDrag"
          @wheel.prevent="onWheel"
        />
        <div v-else-if="loadError" class="iv-loading">
          <p class="iv-error-text">{{ loadError }}</p>
        </div>
        <div v-else class="iv-loading">
          <div class="iv-spinner"></div>
          <p>加载中...</p>
        </div>
      </div>
    </div>
    <template #statusbar>
      <span v-if="loadError" class="iv-error">{{ loadError }}</span>
      <span v-else-if="imageSrc">缩放: {{ Math.round(scale * 100) }}%</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
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

function getDownloadUrl(fileId: number): string {
  return `/api/files/download/${fileId}`
}

const fileName = ref('')
const imageSrc = ref('')
const scale = ref(1)
const translateX = ref(0)
const translateY = ref(0)
const viewportRef = ref<HTMLElement | null>(null)
const isDragging = ref(false)
const dragStartX = ref(0)
const dragStartY = ref(0)
const loadError = ref('')

const imageStyle = computed(() => ({
  transform: `translate(${translateX.value}px, ${translateY.value}px) scale(${scale.value})`,
}))

async function loadImage(fileId: number) {
  try {
    loadError.value = ''
    const url = getDownloadUrl(fileId)
    const resp = await fetch(url, { headers: authHeaders() })
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
    const blob = await resp.blob()
    if (imageSrc.value) URL.revokeObjectURL(imageSrc.value)
    imageSrc.value = URL.createObjectURL(blob)
    scale.value = 1
    translateX.value = 0
    translateY.value = 0
  } catch (e: any) {
    loadError.value = e.message || '图片加载失败'
  }
}

function zoomIn() {
  scale.value = Math.min(scale.value * 1.25, 5)
}

function zoomOut() {
  scale.value = Math.max(scale.value / 1.25, 0.1)
}

function fitToWindow() {
  scale.value = 1
  translateX.value = 0
  translateY.value = 0
}

function startDrag(e: MouseEvent) {
  isDragging.value = true
  dragStartX.value = e.clientX - translateX.value
  dragStartY.value = e.clientY - translateY.value
}

function doDrag(e: MouseEvent) {
  if (!isDragging.value) return
  translateX.value = e.clientX - dragStartX.value
  translateY.value = e.clientY - dragStartY.value
}

function stopDrag() {
  isDragging.value = false
}

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  scale.value = Math.min(Math.max(scale.value * delta, 0.1), 5)
}

function handleDownload() {
  if (!imageSrc.value) return
  const a = document.createElement('a')
  a.href = imageSrc.value
  a.download = fileName.value
  a.click()
}

onMounted(() => {
  const payload = getPayload()
  if (payload && payload.fileId) {
    fileName.value = payload.fileName || 'image'
    loadImage(payload.fileId)
  }
})

onBeforeUnmount(() => {
  if (imageSrc.value) URL.revokeObjectURL(imageSrc.value)
})
</script>

<style scoped>
.iv-container {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #e8e8e8;
  overflow: hidden;
}

.iv-viewport {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  cursor: grab;
}

.iv-viewport:active {
  cursor: grabbing;
}

.iv-image {
  max-width: none;
  max-height: none;
  user-select: none;
  -webkit-user-drag: none;
}

.iv-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: #999;
  font-size: 14px;
}

.iv-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #e0e0e0;
  border-top-color: #2395bc;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.iv-error {
  color: #e74c3c;
}

.iv-error-text {
  color: #e74c3c;
  font-size: 14px;
}
</style>
