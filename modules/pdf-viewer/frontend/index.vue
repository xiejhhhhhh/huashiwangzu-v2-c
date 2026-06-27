<template>
  <viewer-shell
    :file-name="fileName"
    app-name="PDF 查看器"
    file-icon="📕"
    :show-download="true"
    :show-zoom-in="true"
    :show-zoom-out="true"
    :show-fit="true"
    @download="handleDownload"
    @zoom-in="zoomIn"
    @zoom-out="zoomOut"
    @fit="fitToWindow"
  >
    <template #toolbar-center>
      <div class="pv-pagenav" v-if="pageCount > 0">
        <button class="vs-btn" :disabled="currentPage <= 1" @click="goPage(currentPage - 1)">上一页</button>
        <span class="pv-pagenav-info">
          第 <input class="pv-page-input" type="number" :value="currentPage" @change="onPageInput" min="1" :max="pageCount" /> / {{ pageCount }} 页
        </span>
        <button class="vs-btn" :disabled="currentPage >= pageCount" @click="goPage(currentPage + 1)">下一页</button>
        <button class="vs-btn" @click="toggleSearch" :class="{ active: showSearch }">搜索</button>
      </div>
    </template>
    <div class="pv-container">
      <div v-if="showSearch" class="pv-search-bar">
        <input
          v-model="searchQuery"
          class="pv-search-input"
          placeholder="搜索文本..."
          @keydown.enter="doSearch"
        />
        <button class="vs-btn" @click="doSearch">搜索</button>
        <button class="vs-btn" @click="searchPrev" :disabled="searchMatchCount === 0">▲</button>
        <button class="vs-btn" @click="searchNext" :disabled="searchMatchCount === 0">▼</button>
        <span v-if="searchMatchCount > 0" class="pv-search-count">
          {{ searchIndex + 1 }}/{{ searchMatches.length }}
        </span>
      </div>
      <div v-if="loadError" class="pv-error">{{ loadError }}</div>
      <div v-else class="pv-viewport" ref="viewportRef">
        <div v-for="(_, idx) in renderedPages" :key="idx" class="pv-page-wrapper" :data-page="idx + 1">
          <div class="pv-page-container" :ref="(el) => setPageRef(idx, el)">
            <canvas :ref="(el) => setCanvasRef(idx, el)"></canvas>
            <div class="pv-text-layer" :ref="(el) => setTextLayerRef(idx, el)"></div>
          </div>
        </div>
      </div>
    </div>
    <template #statusbar>
      <span v-if="pageCount > 0">{{ pageCount }} 页</span>
      <span v-if="pdfScale !== 1 && pageCount > 0"> | 缩放: {{ Math.round(pdfScale * 100) }}%</span>
      <span v-if="searchMatchCount > 0" class="pv-search-status"> | 搜索: {{ searchIndex + 1 }}/{{ searchMatches.length }}</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick } from 'vue'
import viewerShell from '@/shared/components/viewer-shell.vue'
import { apiPost, downloadBlob } from './api'

const props = defineProps<{ fileId?: number; fileName?: string; format?: string; mode?: string }>()

function getPayload(): { fileId: number; fileName: string } | null {
  if (props.fileId) return { fileId: Number(props.fileId), fileName: props.fileName || '' }
  const p = (window as any).__MODULE_OPEN_FILE_PAYLOAD__
  if (p?.fileId) return { fileId: p.fileId, fileName: p.fileName || '' }
  return null
}

const fileName = ref('')
const fileBlobUrl = ref('')
const fileId = ref(0)
const pageCount = ref(0)
const currentPage = ref(1)
const pdfScale = ref(1.5)
const loadError = ref('')
const showSearch = ref(false)
const searchQuery = ref('')
const searchMatches = ref<Array<{ page: number; itemIdx: number }>>([])
const searchMatchCount = computed(() => searchMatches.value.length)
const searchIndex = ref(0)
const viewportRef = ref<HTMLElement | null>(null)
const renderedPages = ref<number[]>([])

interface PdfPage {
  getViewport(params: { scale: number }): { width: number; height: number; scale: number }
  render(params: { canvasContext: CanvasRenderingContext2D; viewport: { width: number; height: number; scale: number } }): { promise: Promise<void> }
  getTextContent(): Promise<{ items: Array<{ str: string }> }>
}

interface PdfDoc {
  numPages: number
  getPage(pageNum: number): Promise<PdfPage>
}

interface TextLayerInst {
  textDivs: HTMLElement[]
}

let pdfDoc: PdfDoc | null = null
let canvasRefs: Record<number, HTMLCanvasElement | null> = {}
let textLayerRefs: Record<number, HTMLDivElement | null> = {}
let pageRefs: Record<number, HTMLDivElement | null> = {}
let pageTextLayers: Record<number, TextLayerInst> = {}
let pageTextItems: Array<{ page: number; itemIdx: number; str: string }> = []
let ocrWordsCache: Record<string, OcrData | null> = {}

function setCanvasRef(idx: number, el: unknown) {
  canvasRefs[idx] = el as HTMLCanvasElement | null
}

function setTextLayerRef(idx: number, el: unknown) {
  textLayerRefs[idx] = el as HTMLDivElement | null
}

function setPageRef(idx: number, el: unknown) {
  pageRefs[idx] = el as HTMLDivElement | null
}

async function loadPdf(fid: number) {
  try {
    loadError.value = ''
    fileId.value = fid
    const blob = await downloadBlob(fid)
    fileBlobUrl.value = URL.createObjectURL(blob)

    const pdfjsLib = await import('pdfjs-dist')
    pdfjsLib.GlobalWorkerOptions.workerSrc = '/pdf.worker.min.mjs'
    pdfDoc = await pdfjsLib.getDocument(fileBlobUrl.value).promise as unknown as PdfDoc
    pageCount.value = pdfDoc.numPages
    renderedPages.value = Array.from({ length: pdfDoc.numPages }, (_, i) => i)
    pageTextItems = []
    ocrWordsCache = {}
    pageTextLayers = {}
    await nextTick()
    await renderAllPages()
    await buildTextIndex()
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : 'PDF 加载失败'
  }
}

async function renderAllPages() {
  if (!pdfDoc) return
  const scale = pdfScale.value
  for (let i = 1; i <= pageCount.value; i++) {
    await renderPage(i, scale)
  }
}

async function renderPage(pageNum: number, scale: number) {
  if (!pdfDoc) return
  const page = await pdfDoc.getPage(pageNum)
  const viewport = page.getViewport({ scale })
  const idx = pageNum - 1

  const canvas = canvasRefs[idx]
  if (!canvas) return
  canvas.width = viewport.width
  canvas.height = viewport.height
  const ctx = canvas.getContext('2d')!
  await page.render({ canvasContext: ctx, viewport }).promise

  const textLayerDiv = textLayerRefs[idx]
  if (!textLayerDiv) return
  textLayerDiv.innerHTML = ''
  textLayerDiv.style.width = viewport.width + 'px'
  textLayerDiv.style.height = viewport.height + 'px'
  // pdf.js v4 TextLayer 必须设 --scale-factor,否则每个 span 字号错位、选区不对齐(行高错觉)
  textLayerDiv.style.setProperty('--scale-factor', String(viewport.scale))

  const tc = await page.getTextContent()
  const totalChars = tc.items.reduce((sum: number, item: { str: string }) => sum + item.str.length, 0)

  if (totalChars < 20) {
    await renderOcrTextLayer(textLayerDiv, pageNum, viewport)
  } else {
    const { TextLayer } = await import('pdfjs-dist')
    const textLayer = new (TextLayer as unknown as new (args: Record<string, unknown>) => { render: () => Promise<void>; textDivs: HTMLElement[] })({
      textContentSource: tc,
      container: textLayerDiv,
      viewport: viewport,
    })
    await textLayer.render()
    pageTextLayers[pageNum] = textLayer
  }
}

interface OcrWord { t: string; x: number; y: number; w: number; h: number }
interface OcrData { words: OcrWord[]; img_w?: number; img_h?: number }

async function renderOcrTextLayer(container: HTMLDivElement, pageNum: number, viewport: { width: number; height: number; scale: number }) {
  let ocrData = ocrWordsCache[pageNum]
  if (!ocrData) {
    ocrData = await fetchOcrWords(pageNum)
    ocrWordsCache[pageNum] = ocrData
  }
  if (!ocrData || !ocrData.words || ocrData.words.length === 0) return

  const imgW = ocrData.img_w || 1
  const imgH = ocrData.img_h || 1
  const scaleX = viewport.width / imgW
  const scaleY = viewport.height / imgH
  const baseFontSize = Math.round(14 * scaleY)

  for (let i = 0; i < ocrData.words.length; i++) {
    const w = ocrData.words[i]
    const span = document.createElement('span')
    span.className = 'pv-ocr-word'
    span.textContent = w.t
    span.style.position = 'absolute'
    span.style.left = Math.round(w.x * scaleX) + 'px'
    span.style.top = Math.round(w.y * scaleY) + 'px'
    span.style.fontSize = Math.max(10, Math.round(14 * scaleY)) + 'px'
    span.style.lineHeight = Math.round(w.h * scaleY) + 'px'
    span.style.whiteSpace = 'nowrap'
    span.style.color = 'transparent'
    span.style.pointerEvents = 'auto'
    span.style.cursor = 'text'
    container.appendChild(span)
    pageTextItems.push({ page: pageNum, itemIdx: i, str: w.t })
  }
}

async function fetchOcrWords(pageNum: number): Promise<OcrData | null> {
  try {
    const data = await apiPost<OcrData>('/modules/call', {
      target_module: 'knowledge',
      action: 'get_ocr_words',
      parameters: { file_id: fileId.value, page: pageNum },
    })
    if (data) return data
  } catch (e) {
    console.warn('Failed to fetch OCR words for page', pageNum, e)
  }
  return null
}

async function buildTextIndex() {
  if (!pdfDoc) return
  for (let p = 1; p <= pageCount.value; p++) {
    if (pageTextItems.some((i) => i.page === p)) continue
    const page = await pdfDoc.getPage(p)
    const tc = await page.getTextContent()
    for (let i = 0; i < tc.items.length; i++) {
      const s = (tc.items[i].str || '').trim()
      if (s) {
        pageTextItems.push({ page: p, itemIdx: i, str: s })
      }
    }
  }
}

function toggleSearch() {
  showSearch.value = !showSearch.value
  if (!showSearch.value) {
    clearHighlights()
  } else if (searchMatches.value.length > 0) {
    highlightCurrentMatch()
  }
}

function doSearch() {
  const q = (searchQuery.value || '').trim().toLowerCase()
  if (!q || !pdfDoc) return
  clearHighlights()

  const matches: Array<{ page: number; itemIdx: number }> = []
  for (const item of pageTextItems) {
    if (item.str.toLowerCase().includes(q)) {
      matches.push({ page: item.page, itemIdx: item.itemIdx })
    }
  }
  searchMatches.value = matches
  searchIndex.value = 0
  if (matches.length > 0) {
    nextTick(() => highlightCurrentMatch())
  }
}

function clearHighlights() {
  for (const tl of Object.values(pageTextLayers)) {
    if (tl && tl.textDivs) {
      for (const div of tl.textDivs) {
        div.classList.remove('pv-highlight', 'pv-highlight-current')
      }
    }
  }
  document.querySelectorAll('.pv-ocr-word').forEach((el) => {
    el.classList.remove('pv-highlight', 'pv-highlight-current')
  })
}

function highlightCurrentMatch() {
  clearHighlights()
  const idx = searchIndex.value
  const match = searchMatches.value[idx]
  if (!match) return

  const tl = pageTextLayers[match.page]
  if (tl && tl.textDivs && tl.textDivs[match.itemIdx]) {
    tl.textDivs[match.itemIdx].classList.add('pv-highlight-current')
  } else {
    const container = pageRefs[match.page - 1]
    if (container) {
      const spans = container.querySelectorAll('.pv-ocr-word')
      if (spans[match.itemIdx]) {
        spans[match.itemIdx].classList.add('pv-highlight-current')
      }
    }
  }

  const pageContainer = pageRefs[match.page - 1]
  if (pageContainer) {
    pageContainer.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }
}

function goToMatchPage(matchIdx: number) {
  if (matchIdx < 0 || matchIdx >= searchMatches.value.length) return
  searchIndex.value = matchIdx
  const match = searchMatches.value[matchIdx]
  if (match) {
    currentPage.value = match.page
    nextTick(() => highlightCurrentMatch())
  }
}

function searchPrev() {
  if (searchMatches.value.length === 0) return
  let idx = searchIndex.value - 1
  if (idx < 0) idx = searchMatches.value.length - 1
  goToMatchPage(idx)
}

function searchNext() {
  if (searchMatches.value.length === 0) return
  let idx = searchIndex.value + 1
  if (idx >= searchMatches.value.length) idx = 0
  goToMatchPage(idx)
}

function zoomIn() {
  pdfScale.value = Math.min(pdfScale.value * 1.25, 5)
  nextTick(() => renderAllPages())
}

function zoomOut() {
  pdfScale.value = Math.max(pdfScale.value / 1.25, 0.5)
  nextTick(() => renderAllPages())
}

function fitToWindow() {
  pdfScale.value = 1.5
  nextTick(() => renderAllPages())
}

function goPage(page: number) {
  if (page < 1 || page > pageCount.value) return
  currentPage.value = page
  const el = pageRefs[page - 1]
  if (el) el.scrollIntoView({ behavior: 'smooth' })
}

function onPageInput(e: Event) {
  const val = parseInt((e.target as HTMLInputElement).value)
  if (val >= 1 && val <= pageCount.value) goPage(val)
}

function handleDownload() {
  if (!fileBlobUrl.value) return
  const a = document.createElement('a')
  a.href = fileBlobUrl.value
  a.download = fileName.value
  a.click()
}

onMounted(() => {
  const p = getPayload()
  if (p && p.fileId) {
    fileName.value = p.fileName || 'document.pdf'
    loadPdf(p.fileId)
  }
})
</script>

<style scoped>
.pv-container {
  width: 100%;
  height: 100%;
  background: #e8e8e8;
  display: flex;
  flex-direction: column;
}

.pv-search-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
}

.pv-search-input {
  flex: 1;
  max-width: 300px;
  padding: 5px 10px;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  font-size: 13px;
  outline: none;
}

.pv-search-input:focus {
  border-color: #2395bc;
}

.pv-search-count {
  font-size: 12px;
  color: #888;
}

.pv-search-status {
  font-size: 12px;
  color: #2395bc;
}

.pv-viewport {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 16px;
}

.pv-page-wrapper {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.pv-page-container {
  position: relative;
  box-shadow: 0 1px 6px rgba(0, 0, 0, 0.15);
  background: #fff;
}

.pv-page-container canvas {
  display: block;
  max-width: 100%;
}

.pv-text-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
  user-select: text;
  -webkit-user-select: text;
  overflow: hidden;
  line-height: 1;
}

:deep(.pv-text-layer span) {
  color: transparent !important;
  cursor: text;
  pointer-events: auto;
  position: absolute;
  white-space: pre;
  transform-origin: 0 0;
}

:deep(.pv-ocr-word) {
  position: absolute;
  color: transparent;
  cursor: text;
  pointer-events: auto;
}

:deep(.pv-highlight) {
  background: rgba(255, 255, 0, 0.4) !important;
  border-radius: 2px;
}

:deep(.pv-highlight-current) {
  background: rgba(255, 165, 0, 0.55) !important;
  border-radius: 2px;
}

.pv-pagenav {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pv-pagenav-info {
  font-size: 13px;
  color: #555;
  white-space: nowrap;
}

.pv-page-input {
  width: 50px;
  padding: 2px 6px;
  border: 1px solid #d0d0d0;
  border-radius: 3px;
  font-size: 13px;
  text-align: center;
  outline: none;
}

.pv-page-input:focus {
  border-color: #2395bc;
}

.pv-error {
  padding: 40px;
  text-align: center;
  color: #e74c3c;
  font-size: 14px;
}
</style>
