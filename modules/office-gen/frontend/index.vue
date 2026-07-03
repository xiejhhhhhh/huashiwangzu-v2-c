<template>
  <div class="office-gen-container">
    <div class="og-header">
      <h2>Office Document Generator</h2>
      <p class="og-subtitle">Generate Word, Excel, PowerPoint, and PDF documents from structured data</p>
    </div>

    <div class="og-grid">
      <button
        class="og-card"
        v-for="fmt in formats"
        :key="fmt.key"
        type="button"
        :disabled="generating === fmt.key"
        @click="generateFormat(fmt.key)"
      >
        <div class="og-card-icon">{{ fmt.icon }}</div>
        <div class="og-card-title">{{ fmt.name }}</div>
        <div class="og-card-desc">{{ fmt.desc }}</div>
      </button>
    </div>

    <div v-if="generatedFile" class="og-result">
      <strong>{{ generatedFile.name }}</strong>
      <span>#{{ generatedFile.file_id }} · {{ generatedFile.size }} bytes</span>
    </div>
    <div v-if="errorMessage" class="og-error">{{ errorMessage }}</div>

    <div class="og-status">
      <span class="og-status-dot" :class="{ active: libreofficeOk }"></span>
      {{ generating ? 'Generating...' : libreofficeOk ? 'LibreOffice available' : 'LibreOffice not detected' }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { checkHealth, generateSample } from './api'
import type { GeneratedFile, OfficeFormat } from './api'

const formats: Array<{ key: OfficeFormat; name: string; icon: string; desc: string }> = [
  { key: 'docx', name: 'Word (.docx)', icon: '📄', desc: 'Generate Word documents with headings, paragraphs, tables and images' },
  { key: 'xlsx', name: 'Excel (.xlsx)', icon: '📊', desc: 'Generate spreadsheets with multiple sheets, headers and data rows' },
  { key: 'pptx', name: 'PowerPoint (.pptx)', icon: '📽️', desc: 'Generate presentations with slides, bullet points and speaker notes' },
  { key: 'pdf', name: 'PDF (.pdf)', icon: '📕', desc: 'Generate PDF documents with headings, paragraphs and tables' },
]
const libreofficeOk = ref(false)
const generating = ref<OfficeFormat | null>(null)
const generatedFile = ref<GeneratedFile | null>(null)
const errorMessage = ref('')

async function generateFormat(fmt: OfficeFormat) {
  generating.value = fmt
  generatedFile.value = null
  errorMessage.value = ''
  try {
    generatedFile.value = await generateSample(fmt)
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'Generation failed'
  } finally {
    generating.value = null
  }
}

onMounted(async () => {
  try {
    const data = await checkHealth()
    libreofficeOk.value = !!data.libreoffice
  } catch {
    // offline
  }
})
</script>

<style scoped>
.office-gen-container {
  padding: 24px;
  color: #333;
  font-family: '苹方', 'Microsoft YaHei', '宋体', sans-serif;
}
.og-header h2 {
  margin: 0 0 6px;
  font-size: 22px;
  color: #2395bc;
}
.og-subtitle {
  margin: 0 0 24px;
  color: #666;
  font-size: 14px;
}
.og-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.og-card {
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  transition: all 0.2s;
  text-align: left;
}
.og-card:hover {
  border-color: #2395bc;
  box-shadow: 0 2px 12px rgba(35, 149, 188, 0.12);
}
.og-card:disabled {
  cursor: progress;
  opacity: 0.7;
}
.og-card-icon {
  font-size: 32px;
  margin-bottom: 10px;
}
.og-card-title {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 6px;
}
.og-card-desc {
  font-size: 12px;
  color: #999;
  line-height: 1.5;
}
.og-status {
  font-size: 13px;
  color: #999;
  display: flex;
  align-items: center;
  gap: 8px;
}
.og-result,
.og-error {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 8px;
  font-size: 13px;
}
.og-result {
  display: flex;
  flex-direction: column;
  gap: 4px;
  border: 1px solid #b7eb8f;
  background: #f6ffed;
  color: #2f6f13;
}
.og-error {
  border: 1px solid #ffa39e;
  background: #fff1f0;
  color: #a8071a;
}
.og-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ccc;
}
.og-status-dot.active {
  background: #52c41a;
}
</style>
