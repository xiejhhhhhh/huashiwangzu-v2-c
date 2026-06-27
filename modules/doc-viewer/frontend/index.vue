<template>
  <viewer-shell
    :file-name="fileName"
    app-name="文档查看器"
    file-icon="📄"
    :show-download="true"
    @download="handleDownload"
  >
    <div class="dv-container">
      <div v-if="loadError" class="dv-error">{{ loadError }}</div>
      <div v-else-if="loading" class="dv-loading">
        <div class="iv-spinner"></div>
        <p>解析文档中...</p>
      </div>
      <div v-else class="dv-content">
        <div v-for="(block, idx) in contentBlocks" :key="idx" class="dv-block" :class="`dv-${block.type}`">
          <div v-if="block.type === 'paragraph'" class="dv-paragraph">{{ block.content }}</div>
          <table v-else-if="block.type === 'table'" class="dv-table">
            <tr v-for="(row, ri) in block.rows" :key="ri">
              <td v-for="(cell, ci) in row.cells" :key="ci">{{ cell }}</td>
            </tr>
          </table>
        </div>
      </div>
    </div>
    <template #statusbar>
      <span v-if="contentBlocks.length > 0">{{ contentBlocks.length }} 个内容块</span>
    </template>
  </viewer-shell>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import viewerShell from '@/shared/components/viewer-shell.vue'
import { apiPost, downloadBlob } from './api'

const props = defineProps<{ fileId?: number; fileName?: string; format?: string; mode?: string }>()

function getPayload(): { fileId: number; fileName: string } | null {
  // 框架通过 <component v-bind="payload"> 把 fileId 作为 prop 传进来
  if (props.fileId) return { fileId: Number(props.fileId), fileName: props.fileName || '' }
  const p = (window as any).__MODULE_OPEN_FILE_PAYLOAD__
  if (p?.fileId) return { fileId: p.fileId, fileName: p.fileName || '' }
  return null
}

const fileName = ref('')
const loading = ref(true)
const loadError = ref('')
interface DocBlock {
  type: string
  content?: string
  rows?: Array<{ cells: string[] }>
}

const contentBlocks = ref<DocBlock[]>([])
const fileBlobUrl = ref('')

async function loadDoc(fid: number) {
  try {
    loadError.value = ''
    loading.value = true
    interface ParseResponse { content?: DocBlock[] }
    const data = await apiPost<ParseResponse>('/modules/call', {
      target_module: 'docx-parser',
      action: 'parse',
      parameters: { file_id: fid },
    })
    const content = data?.content || []
    contentBlocks.value = content
  } catch (e: unknown) {
    loadError.value = e instanceof Error ? e.message : '文档解析失败'
  } finally {
    loading.value = false
  }
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
    fileName.value = payload.fileName || 'document.docx'
    try {
      const blob = await downloadBlob(payload.fileId)
      fileBlobUrl.value = URL.createObjectURL(blob)
    } catch { /* download not available */ }
    loadDoc(payload.fileId)
  }
})
</script>

<style scoped>
.dv-container {
  width: 100%;
  height: 100%;
  overflow-y: auto;
  background: #fff;
}

.dv-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
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

.dv-content {
  padding: 24px 32px;
  max-width: 800px;
  margin: 0 auto;
}

.dv-block {
  margin-bottom: 10px;
}

.dv-paragraph {
  font-size: 14px;
  line-height: 1.8;
  color: #333;
}

.dv-table {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 13px;
  border: 1px solid #e0e0e0;
}

.dv-table td {
  border: 1px solid #e0e0e0;
  padding: 6px 10px;
  color: #333;
}

.dv-table tr:nth-child(even) td {
  background: #f9f9f9;
}

.dv-error {
  padding: 40px;
  text-align: center;
  color: #e74c3c;
  font-size: 14px;
}
</style>
