<template>
  <div class="excel-editor">
    <!-- Loading -->
    <div v-if="loading" class="state-layer">
      <span class="loading-spinner"></span>
      <p>加载 Excel 数据…</p>
    </div>

    <!-- Error -->
    <div v-else-if="errorMsg" class="state-layer">
      <p class="error-text">{{ errorMsg }}</p>
      <button v-if="retryable" class="retry-btn" @click="init">重试</button>
    </div>

    <!-- Editor -->
    <template v-else-if="stateKey">
      <!-- Toolbar -->
      <ExcelToolbar
        :activeStyles="activeStyles"
        @action="onToolbarAction"
        @style-change="onStyleChange" />

      <!-- Sheet tabs -->
      <div class="sheet-bar">
        <button
          v-for="(name, idx) in allSheets"
          :key="idx"
          :class="{ active: currentSheetIndex === idx }"
          @click="switchSheet(idx)">
          {{ name || ('Sheet' + (idx + 1)) }}
        </button>
      </div>

      <!-- Grid -->
      <ExcelGrid
        ref="gridRef"
        :cells="cells"
        :styles="cellStyles"
        :merges="merges"
        :colWidths="colWidths"
        :rowHeights="rowHeights"
        :totalRows="totalRows"
        :totalCols="totalCols"
        :isEditing="isEditing"
        :editAddr="editAddr"
        :editValue="editValue"
        :selectedAddr="selectedAddr"
        :selectedRange="selectedRange"
        :showFormulaBar="true"
        :formulaValue="formulaValue"
        @cell-click="onCellClick"
        @cell-dblclick="startEdit"
        @cell-contextmenu="onCellContextMenu"
        @header-contextmenu="onHeaderContextMenu"
        @select-range="onSelectRange"
        @confirm-edit="confirmEdit"
        @cancel-edit="cancelEdit"
        @update:editValue="editValue = $event"
        @update:formulaValue="formulaValue = $event"
        @formula-enter="onFormulaEnter"
        @tab-edit="onTabEdit" />

      <!-- History panel -->
      <HistoryPanel
        v-if="showHistory"
        :list="historyList"
        @close="showHistory = false"
        @preview="previewHistory" />
    </template>

    <!-- Context menu -->
    <ContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      @action="execContextAction" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { getApiUrl } from '../runtime'
import { colLetter, parseCellAddr } from './components/address-util'
import ExcelGrid from './components/ExcelGrid.vue'
import ExcelToolbar from './components/ExcelToolbar.vue'
import ContextMenu from './components/ContextMenu.vue'
import HistoryPanel from './components/HistoryPanel.vue'
import * as api from './components/api-service'
import type { EditResult, SheetData, HistoryItem } from './components/api-service'

// ── State ──
const loading = ref(true)
const errorMsg = ref('')
const retryable = ref(false)
const stateKey = ref('')
const cells = ref<Record<string, string>>({})
const cellStyles = ref<Record<string, Record<string, unknown>>>({})
const merges = ref<Record<string, { topLeft: string; rows: number; cols: number }>>({})
const colWidths = ref<Record<string, number>>({})
const rowHeights = ref<Record<string, number>>({})
const totalRows = ref(40)
const totalCols = ref(10)
const allSheets = ref<string[]>(['Sheet1'])
const currentSheetIndex = ref(0)
const sheetSet = ref<Record<string, unknown>>({})

// Selection & editing
const selectedAddr = ref('')
const selectedRange = ref<string[]>([])
const isEditing = ref(false)
const editAddr = ref('')
const editValue = ref('')
const formulaValue = ref('')
const showFormulaBar = ref(true)

// History
const showHistory = ref(false)
const historyList = ref<HistoryItem[]>([])

// Context menu
const contextMenu = ref({ visible: false, x: 0, y: 0, addr: '' })
const showSubMenu = ref('')

// Clipboard tracking
const clipboardData = ref<Record<string, { text: string; style: Record<string, unknown> }>>({})
const clipboardRange = ref<string[]>([])

// Grid ref
const gridRef = ref()
const historyPanelRef = ref<HTMLElement>()

// ── Computed ──
const currentSheetName = computed(() => allSheets.value[currentSheetIndex.value] || 'Sheet1')

const activeStyles = computed(() => {
  const addr = selectedAddr.value
  if (!addr) return {}
  return cellStyles.value[addr] || {}
})

// ── Initialization ──
onMounted(async () => {
  document.addEventListener('click', closeContextMenu)
  document.addEventListener('keydown', onGlobalKeydown)
  await init()
})

onUnmounted(() => {
  document.removeEventListener('click', closeContextMenu)
  document.removeEventListener('keydown', onGlobalKeydown)
})

async function init() {
  loading.value = true
  errorMsg.value = ''
  retryable.value = false

  try {
    // Check if we have a file payload from the desktop shell
    const payload = await tryGetFilePayload()
    if (payload) {
      await openFile(payload.fileId, payload.fileName)
    } else {
      // Try URL params
      const params = new URLSearchParams(window.location.search)
      const fileId = params.get('fileId')
      if (fileId) {
        await openFile(Number(fileId), params.get('fileName') || '')
      } else {
        // Demo mode - use states
        stateKey.value = 'demo'
        loading.value = false
      }
    }
  } catch (e: unknown) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
    retryable.value = true
  } finally {
    loading.value = false
  }
}

async function tryGetFilePayload(): Promise<{ fileId: number; fileName: string } | null> {
  try {
    const payload = (window as any).__MODULE_OPEN_FILE_PAYLOAD__
    if (payload?.fileId) {
      return { fileId: payload.fileId, fileName: payload.fileName || '' }
    }
  } catch {}
  return null
}

async function openFile(fileId: number, fileName: string) {
  stateKey.value = `knowledge_${fileId}`
  try {
    const json = await api.openFile(fileId)
    applyState(json)
    return
  } catch {}
  try {
    const data = await api.parseFile(fileId)
    applyParseResult(data)
  } catch {}
}

function applyState(data: EditResult & { all_sheets?: string[]; sheet_set?: Record<string, unknown>; state_key?: string }) {
  cells.value = data.cells || {}
  cellStyles.value = data.styles || {}
  merges.value = data.merges || {}
  colWidths.value = (data as Record<string, unknown>).col_widths as Record<string, number> || {}
  rowHeights.value = (data as Record<string, unknown>).row_heights as Record<string, number> || {}
  totalRows.value = data.total_rows || 40
  totalCols.value = data.total_cols || 10
  allSheets.value = data.all_sheets || ['Sheet1']
  sheetSet.value = (data as Record<string, unknown>).sheet_set as Record<string, unknown> || {}
}

function applyParseResult(data: EditResult & { sheet_set?: Record<string, SheetData>; all_sheets?: string[] }) {
  if (data.sheet_set) {
    const firstSheet = Object.keys(data.sheet_set)[0] || 'Sheet1'
    const sheetData = data.sheet_set[firstSheet]
    cells.value = sheetData.cells || {}
    cellStyles.value = sheetData.styles || {}
    merges.value = sheetData.merges || {}
    colWidths.value = sheetData.col_widths || {}
    rowHeights.value = sheetData.row_heights || {}
    totalRows.value = sheetData.total_rows || 40
    totalCols.value = sheetData.total_cols || 10
    allSheets.value = data.all_sheets || [firstSheet]
    sheetSet.value = data.sheet_set as unknown as Record<string, unknown>
  } else {
    cells.value = data.cells || {}
    cellStyles.value = data.styles || {}
    merges.value = data.merges || {}
    colWidths.value = (data as Record<string, unknown>).col_widths as Record<string, number> || {}
    rowHeights.value = (data as Record<string, unknown>).row_heights as Record<string, number> || {}
    totalRows.value = data.total_rows || 40
    totalCols.value = data.total_cols || 10
  }
}

// ── Sheet switching ──
function switchSheet(idx: number) {
  currentSheetIndex.value = idx
  const name = allSheets.value[idx]
  const sd = sheetSet.value[name] as SheetData | undefined
  if (sd) {
    cells.value = sd.cells || {}
    cellStyles.value = sd.styles || {}
    merges.value = sd.merges || {}
    colWidths.value = sd.col_widths || {}
    rowHeights.value = sd.row_heights || {}
    totalRows.value = sd.total_rows || 40
    totalCols.value = sd.total_cols || 10
  } else if (stateKey.value) {
    loadSheetFromBackend(name)
  }
  selectedAddr.value = ''
  selectedRange.value = []
  isEditing.value = false
}

async function loadSheetFromBackend(name: string) {
  // Will be implemented with API dispatch
}

// ── Cell selection & editing ──
function onCellClick(addr: string) {
  if (isEditing.value) {
    confirmEdit()
  }
  selectedAddr.value = addr
  selectedRange.value = [addr]
  formulaValue.value = cells.value[addr] || ''
  contextMenu.value.visible = false
}

function startEdit(addr: string) {
  selectedAddr.value = addr
  selectedRange.value = [addr]
  editAddr.value = addr
  editValue.value = cells.value[addr] || ''
  formulaValue.value = editValue.value
  isEditing.value = true
}

function confirmEdit() {
  if (!isEditing.value || !editAddr.value) return
  const newVal = editValue.value
  const oldVal = cells.value[editAddr.value] || ''
  if (newVal !== oldVal) {
    cells.value[editAddr.value] = newVal
    // Send to backend
    sendEdit('input', editAddr.value, newVal)
  }
  isEditing.value = false
  editAddr.value = ''
  formulaValue.value = newVal
}

function cancelEdit() {
  isEditing.value = false
  editAddr.value = ''
}

function onTabEdit(shift: boolean) {
  if (!editAddr.value) return
  confirmEdit()
  const parsed = parseCellAddr(editAddr.value)
  const newCol = shift ? parsed.col - 1 : parsed.col + 1
  if (newCol >= 0 && newCol < totalCols.value) {
    const newAddr = `${colLetter(newCol)}${parsed.row + 1}`
    startEdit(newAddr)
  }
}

function onFormulaEnter() {
  if (selectedAddr.value) {
    const val = formulaValue.value
    cells.value[selectedAddr.value] = val
    sendEdit('input', selectedAddr.value, val)
  }
}

function onFormulaInput(val: string) {
  formulaValue.value = val
}

// ── Toolbar actions ──
async function onToolbarAction(action: string) {
  switch (action) {
    case 'undo':
      await sendStateOp('undo')
      break
    case 'redo':
      await sendStateOp('redo')
      break
    case 'save':
      await sendSave()
      break
    case 'export':
      await exportXlsx()
      break
    case 'bold':
    case 'italic':
    case 'underline':
    case 'strikethrough':
    case 'align_left':
    case 'align_center':
    case 'align_right':
    case 'merge':
    case 'wrap_text':
      await sendStyleAction(action)
      break
  }
}

async function onStyleChange(method: string, params: Record<string, unknown>) {
  if (selectedRange.value.length === 0) return
  await api.editStyle({ state_key: stateKey.value, sheet: currentSheetName.value, address_list: selectedRange.value, method, params })
}

// ── API calls ──
async function sendEdit(method: string, addr: string, value: string) {
  if (!stateKey.value) return
  try {
    await api.editCell({ state_key: stateKey.value, sheet: currentSheetName.value, address: addr, method, value })
  } catch {}
}

async function sendStyleAction(method: string) {
  if (!stateKey.value || selectedRange.value.length === 0) return
  try {
    await api.editStyle({ state_key: stateKey.value, sheet: currentSheetName.value, address_list: selectedRange.value, method, params: {} })
  } catch {}
}

async function sendStateOp(method: string) {
  if (!stateKey.value) return
  try {
    const data = await api.stateOp({ module: 'state', method, params: {}, state_key: stateKey.value, sheet: currentSheetName.value })
    if (data.cells) cells.value = data.cells
    if (data.styles) cellStyles.value = data.styles
  } catch {}
}

async function sendSave() {
  // State is auto-persisted on every write operation
  // This is a manual save trigger
}

async function exportXlsx() {
  if (!stateKey.value) return
  window.open(getApiUrl(`/excel-engine/download/${stateKey.value}`), '_blank')
}

// ── Context menu ──
function onCellContextMenu(addr: string, event: MouseEvent) {
  selectedAddr.value = addr
  contextMenu.value = { visible: true, x: event.clientX, y: event.clientY, addr: addr }
}

function onHeaderContextMenu(type: 'row' | 'col', index: number, event: MouseEvent) {
  contextMenu.value = { visible: false, x: 0, y: 0, addr: '' } // Placeholder
}

function closeContextMenu() {
  contextMenu.value.visible = false
  showSubMenu.value = ''
}

async function execContextAction(action: string) {
  closeContextMenu()
  const addrs = selectedRange.value
  if (addrs.length === 0) return

  switch (action) {
    case 'copy':
      clipboardData.value = {}
      for (const addr of addrs) {
        clipboardData.value[addr] = {
          text: cells.value[addr] || '',
          style: cellStyles.value[addr] || {},
        }
      }
      clipboardRange.value = [...addrs]
      break
    case 'paste':
      if (Object.keys(clipboardData.value).length === 0) return
      const pasteData: string[][] = [[]]
      const sortedKeys = Object.keys(clipboardData.value)
      for (let i = 0; i < sortedKeys.length; i++) {
        const key = sortedKeys[i]
        if (i === 0) {
          pasteData[0].push(clipboardData.value[key].text)
        }
      }
      await api.clipboardOp({ state_key: stateKey.value, sheet: currentSheetName.value, address: contextMenu.value.addr || addrs[0], address_list: [contextMenu.value.addr || addrs[0]], method: 'paste', params: { data: pasteData } })
      break
    case 'clear_all':
      for (const addr of addrs) {
        delete cells.value[addr]
        delete cellStyles.value[addr]
      }
      break
    case 'clear_content':
      for (const addr of addrs) {
        delete cells.value[addr]
      }
      break
    case 'clear_format':
      for (const addr of addrs) {
        delete cellStyles.value[addr]
      }
      break
    case 'merge':
      if (addrs.length >= 2) {
        await sendStyleAction('merge')
      }
      break
  }
}

function onSelectRange(addrs: string[]) {
  selectedRange.value = addrs
}

// ── Keyboard shortcuts (1:1 from old editor) ──
function onGlobalKeydown(e: KeyboardEvent) {
  if (e.ctrlKey || e.metaKey) {
    switch (e.key.toLowerCase()) {
      case 'z':
        e.preventDefault()
        if (e.shiftKey) sendStateOp('redo')
        else sendStateOp('undo')
        break
      case 'y':
        e.preventDefault()
        sendStateOp('redo')
        break
      case 'b':
        e.preventDefault()
        sendStyleAction('bold')
        break
      case 'i':
        e.preventDefault()
        sendStyleAction('italic')
        break
      case 'u':
        e.preventDefault()
        sendStyleAction('underline')
        break
      case 'c':
        if (!isEditing.value) {
          execContextAction('copy')
        }
        break
      case 'v':
        if (!isEditing.value) {
          execContextAction('paste')
        }
        break
      case 's':
        e.preventDefault()
        sendSave()
        break
    }
  }
  if (e.key === 'Delete' && !isEditing.value) {
    if (selectedRange.value.length > 0) {
      for (const addr of selectedRange.value) {
        delete cells.value[addr]
      }
    }
  }
}

// ── History panel (1:1 from old 历史面板.js) ──
function toggleHistory() {
  showHistory.value = !showHistory.value
  if (showHistory.value) {
    loadHistory()
  }
}

async function loadHistory() {
  if (!stateKey.value) return
  try {
    const data = await api.stateOp({ module: 'state', method: 'history_list', params: {}, state_key: stateKey.value, sheet: currentSheetName.value })
    historyList.value = data.history || []
  } catch {}
}

async function previewHistory(historyId: number) {
  if (!stateKey.value) return
  try {
    const data = await api.stateOp({ module: 'state', method: 'history_preview', params: { history_id: historyId }, state_key: stateKey.value, sheet: currentSheetName.value })
    if (data.cells) cells.value = data.cells
    if (data.styles) cellStyles.value = data.styles
    if (data.merges) merges.value = data.merges
    if (data.total_rows) totalRows.value = data.total_rows
    if (data.total_cols) totalCols.value = data.total_cols
  } catch {}
}

function historyIcon(action: string): string {
  const icons: Record<string, string> = {
    '输入': '✏️', '批量填充': '📝', '清除': '🗑️', '超链接': '🔗', '设置格式': '📐',
    '加粗': '𝐁', '倾斜': '𝐼', '下划线': 'U̲', '删除线': 'S̶',
    '左对齐': '≡', '居中': '≡', '右对齐': '≡',
    '设置字体': '🔤', '设置字号': '🔡', '填充色': '🎨', '字体色': '🎨', '换行': '↩️', '边框': '🔲',
    '粘贴': '📋', '合并': '🔗', '排序': '↕️',
    '删除行': '➖', '删除列': '︱',
    '插入行上': '🔼', '插入行下': '🔽', '插入列左': '◀️', '插入列右': '▶️',
    '保存版本': '💾',
  }
  return icons[action] || '⚡'
}

function formatTime(isoStr: string): string {
  if (!isoStr) return ''
  return isoStr.replace('T', ' ').substring(0, 16)
}

// Watch for file open payload
watch(() => (window as any).__MODULE_OPEN_FILE_PAYLOAD__, (payload) => {
  if (payload?.fileId) {
    openFile(payload.fileId, payload.fileName || '')
  }
})
</script>

<style scoped>
.excel-editor {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  overflow: hidden;
  position: relative;
}

.state-layer {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: 12px;
  color: #909399;
  padding: 20px;
  text-align: center;
}

.spin {
  animation: spin 1.5s linear infinite;
}

.loading-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid #e4e7ed;
  border-top-color: #409eff;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.retry-btn {
  padding: 6px 16px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s;
}
.retry-btn:hover {
  border-color: #409eff;
  color: #409eff;
  background: #ecf5ff;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

.error-text {
  color: #f56c6c;
  font-size: 14px;
  margin: 0;
}

/* Sheet tabs */
.sheet-bar {
  display: flex;
  gap: 0;
  border-bottom: 1px solid #e8e8e8;
  background: #f5f5f5;
  flex-shrink: 0;
  overflow-x: auto;
}
.sheet-bar button {
  padding: 6px 16px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-size: 12px;
  color: #666;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}
.sheet-bar button:hover { background: #eaeaea; }
.sheet-bar button.active {
  background: #fff;
  color: #409eff;
  border-bottom-color: #409eff;
  font-weight: 500;
}

/* History panel (1:1 from old 历史面板.js) */
.history-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: 240px;
  height: 100%;
  background: #f8f9fa;
  border-left: 1px solid #d0d0d0;
  display: flex;
  flex-direction: column;
  z-index: 100;
  box-shadow: -2px 0 8px rgba(0,0,0,0.1);
}
.history-header {
  padding: 10px 12px;
  font-size: 12px;
  font-weight: 600;
  color: #333;
  border-bottom: 1px solid #e0e0e0;
  background: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.history-close {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 14px;
  color: #999;
  padding: 2px;
}
.history-close:hover { color: #333; }
.history-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px;
}
.history-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  margin: 2px 0;
  border-radius: 5px;
  cursor: pointer;
  font-size: 11px;
  background: #fff;
  border: 1px solid #eee;
  transition: background 0.15s, border-color 0.15s;
}
.history-item:hover {
  background: #e8f0fe;
  border-color: #4a90d9;
}
.history-icon { font-size: 12px; flex-shrink: 0; }
.history-info { flex: 1; min-width: 0; }
.history-action { font-weight: 500; color: #333; }
.history-desc { color: #666; font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.history-time { font-size: 9px; color: #aaa; flex-shrink: 0; }
.history-empty { padding: 12px; text-align: center; color: #999; font-size: 11px; }

/* Context menu */
.context-menu {
  position: fixed;
  z-index: 1000;
  background: #fff;
  border: 1px solid #d0d0d0;
  border-radius: 8px;
  box-shadow: 2px 2px 12px rgba(0,0,0,0.12);
  min-width: 160px;
  padding: 4px 0;
}
.cm-section {
  padding: 2px 0;
  border-bottom: 1px solid #eee;
}
.cm-section:last-child { border-bottom: none; }
.cm-item {
  padding: 6px 14px;
  font-size: 12px;
  color: #333;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: relative;
}
.cm-item:hover { background: #e8f0fe; }
.cm-has-sub { position: relative; }
.cm-sub {
  position: absolute;
  left: 100%;
  top: -4px;
  background: #fff;
  border: 1px solid #d0d0d0;
  border-radius: 6px;
  box-shadow: 2px 2px 8px rgba(0,0,0,0.1);
  min-width: 120px;
  z-index: 1001;
}
</style>
