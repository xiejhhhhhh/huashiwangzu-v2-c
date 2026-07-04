<template>
  <div v-if="references.length" class="evidence-list" :class="{ 'evidence-list--dense': dense }">
    <article
      v-for="(ref, index) in references"
      :key="evidenceReferenceKey(ref, index)"
      class="evidence-card"
      :class="{ 'evidence-card--openable': canOpenEvidenceReference(ref) }"
    >
      <div class="evidence-card__main">
        <div class="evidence-card__top">
          <span class="evidence-card__type">{{ evidenceReferenceLabel(ref) }}</span>
          <span v-if="ref.status" class="evidence-card__status">{{ ref.status }}</span>
        </div>
        <div class="evidence-card__id" :title="ref.ref_id">{{ ref.ref_key }}: {{ ref.ref_id }}</div>
        <div v-if="referenceSource(ref)" class="evidence-card__source">
          来源 {{ referenceSource(ref) }}
        </div>
        <div v-if="ref.snippet || ref.excerpt" class="evidence-card__snippet">
          {{ ref.snippet || ref.excerpt }}
        </div>
      </div>
      <div class="evidence-card__actions">
        <button
          v-if="canOpenEvidenceReference(ref)"
          type="button"
          class="evidence-card__action"
          :disabled="openingKey === evidenceReferenceKey(ref, index)"
          @click="openReference(ref, index)"
        >
          {{ openingKey === evidenceReferenceKey(ref, index) ? '打开中' : '打开' }}
        </button>
        <button
          v-if="canDownloadReference(ref)"
          type="button"
          class="evidence-card__action"
          :disabled="openingKey === evidenceReferenceKey(ref, index)"
          @click="downloadReference(ref, index)"
        >
          下载
        </button>
        <span
          v-else
          class="evidence-card__reason"
          :title="evidenceReferenceOpenReason(ref)"
        >
          暂不可直接打开
        </span>
        <button
          type="button"
          class="evidence-card__action evidence-card__action--secondary"
          @click="copyReferenceId(ref)"
        >
          复制 ID
        </button>
        <button
          type="button"
          class="evidence-card__action evidence-card__action--secondary"
          @click="copyReference(ref)"
        >
          复制引用
        </button>
        <button
          type="button"
          class="evidence-card__action evidence-card__action--secondary"
          @click="loadMetadata(ref)"
        >
          metadata
        </button>
      </div>
    </article>
    <p v-if="openError" class="evidence-list__error">{{ openError }}</p>
    <p v-if="copyMessage" class="evidence-list__hint">{{ copyMessage }}</p>
    <pre v-if="metadataText" class="evidence-list__metadata">{{ metadataText }}</pre>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetchRaw, apiGet, apiPost } from '../api'
import {
  canOpenEvidenceReference,
  evidenceReferenceCitation,
  evidenceReferenceKey,
  evidenceReferenceLabel,
  evidenceReferenceOpenReason,
  numericFileId,
  type EvidenceReference,
} from './evidenceReferences'

defineProps<{
  references: EvidenceReference[]
  dense?: boolean
}>()

const openingKey = ref('')
const openError = ref('')
const copyMessage = ref('')
const metadataText = ref('')

interface ArtifactExportResult {
  file_id?: number
  url?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function referenceSource(ref: EvidenceReference): string {
  return [ref.source_module, ref.source_tool || ref.source].filter(Boolean).join(' / ')
}

async function copyReferenceId(ref: EvidenceReference) {
  const payload = [ref.source_module, ref.ref_key, ref.ref_id].filter(Boolean).join(':')
  try {
    await navigator.clipboard.writeText(payload)
    copyMessage.value = `已复制 ${payload}`
    window.setTimeout(() => { copyMessage.value = '' }, 1800)
  } catch {
    copyMessage.value = '复制失败'
  }
}

async function copyReference(ref: EvidenceReference) {
  const payload = evidenceReferenceCitation(ref)
  try {
    await navigator.clipboard.writeText(payload)
    copyMessage.value = `已复制 ${payload}`
    window.setTimeout(() => { copyMessage.value = '' }, 1800)
  } catch {
    copyMessage.value = '复制失败'
  }
}

function canDownloadReference(ref: EvidenceReference): boolean {
  return Boolean(ref.download_url || numericFileId(ref) !== null || ref.ref_key === 'artifact_id')
}

async function openBlobPath(path: string) {
  const response = await apiFetchRaw(path)
  if (!response.ok) throw new Error(`接口返回 ${response.status}`)
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  window.open(objectUrl, '_blank', 'noopener')
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
}

async function openReference(ref: EvidenceReference, index: number) {
  const key = evidenceReferenceKey(ref, index)
  openingKey.value = key
  openError.value = ''
  try {
    if (ref.open_url) {
      await openBlobPath(ref.open_url.replace(/^\/api/, ''))
      return
    }
    if (ref.download_url) {
      await openBlobPath(ref.download_url.replace(/^\/api/, ''))
      return
    }
    const fileId = numericFileId(ref)
    if (fileId === null) throw new Error(evidenceReferenceOpenReason(ref))
    await openBlobPath(`/files/preview/${fileId}`)
  } catch (error: unknown) {
    openError.value = error instanceof Error ? error.message : '打开文件失败'
  } finally {
    openingKey.value = ''
  }
}

async function downloadReference(ref: EvidenceReference, index: number) {
  const key = evidenceReferenceKey(ref, index)
  openingKey.value = key
  openError.value = ''
  try {
    if (ref.download_url) {
      await openBlobPath(ref.download_url.replace(/^\/api/, ''))
      return
    }
    const fileId = numericFileId(ref)
    if (fileId !== null) {
      await openBlobPath(`/files/download/${fileId}`)
      return
    }
    if (ref.ref_key === 'artifact_id') {
      const exported = await apiPost<ArtifactExportResult>(`/artifacts/${ref.ref_id}/export`, {})
      if (exported.url) {
        await openBlobPath(exported.url.replace(/^\/api/, ''))
        return
      }
      if (exported.file_id) {
        await openBlobPath(`/files/download/${exported.file_id}`)
        return
      }
    }
    throw new Error(evidenceReferenceOpenReason(ref))
  } catch (error: unknown) {
    openError.value = error instanceof Error ? error.message : '下载失败'
  } finally {
    openingKey.value = ''
  }
}

async function loadMetadata(ref: EvidenceReference) {
  openError.value = ''
  metadataText.value = ''
  try {
    let payload: unknown
    if (ref.ref_key === 'artifact_id') {
      payload = await apiGet<unknown>(`/artifacts/${ref.ref_id}`)
    } else if (ref.ref_key === 'package_id') {
      payload = await apiGet<unknown>(`/content/packages/${ref.ref_id}/full`)
    } else if (ref.ref_key === 'document_id') {
      payload = await apiGet<unknown>(`/knowledge/documents/${ref.ref_id}`)
    } else if (ref.ref_key === 'chunk_id') {
      payload = await apiGet<unknown>(`/knowledge/chunks/${ref.ref_id}`)
    } else {
      const fileId = numericFileId(ref)
      if (fileId === null) {
        payload = {
          reason: evidenceReferenceOpenReason(ref),
          reference: ref,
        }
      } else {
        payload = await apiGet<unknown>(`/files/detail/${fileId}`)
      }
    }
    metadataText.value = JSON.stringify(isRecord(payload) ? payload : { value: payload }, null, 2)
  } catch (error: unknown) {
    openError.value = error instanceof Error ? error.message : 'metadata 加载失败'
  }
}
</script>

<style scoped>
.evidence-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: var(--ag-space-xs);
  min-width: 0;
}
.evidence-list--dense {
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
}
.evidence-card {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--ag-space-sm);
  padding: var(--ag-space-sm);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
}
.evidence-card--openable {
  border-color: #b7d9ec;
  background: #f5fbff;
}
.evidence-card__main {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.evidence-card__actions {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
}
.evidence-card__top {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.evidence-card__type {
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-xs);
  font-weight: 600;
}
.evidence-card__status {
  max-width: 96px;
  padding: 1px 5px;
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-active);
  color: var(--ag-primary-dark);
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.evidence-card__id,
.evidence-card__source,
.evidence-card__reason {
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-xs);
  line-height: var(--ag-line-height-base);
  word-break: break-word;
}
.evidence-card__id {
  font-family: var(--ag-font-mono);
}
.evidence-card__source {
  color: var(--ag-text-tertiary);
}
.evidence-card__snippet {
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-xs);
  line-height: var(--ag-line-height-base);
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.evidence-card__action {
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--ag-primary);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-primary);
  cursor: pointer;
  font-size: var(--ag-font-size-xs);
}
.evidence-card__action--secondary {
  border-color: var(--ag-border-light);
  color: var(--ag-text-secondary);
}
.evidence-card__action:disabled {
  cursor: default;
  opacity: 0.65;
}
.evidence-card__reason {
  flex-shrink: 0;
  max-width: 96px;
  text-align: right;
}
.evidence-list__error {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--ag-error);
  font-size: var(--ag-font-size-xs);
}
.evidence-list__hint {
  grid-column: 1 / -1;
  margin: 0;
  color: var(--ag-text-secondary);
  font-size: var(--ag-font-size-xs);
}
.evidence-list__metadata {
  grid-column: 1 / -1;
  max-height: 220px;
  overflow: auto;
  margin: 0;
  padding: var(--ag-space-sm);
  border: 1px solid var(--ag-border-light);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-muted);
  color: var(--ag-text-primary);
  font-size: var(--ag-font-size-xs);
  white-space: pre-wrap;
}
</style>
