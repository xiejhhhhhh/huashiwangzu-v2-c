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
        <div v-if="ref.source_tool || ref.source" class="evidence-card__source">
          来源 {{ ref.source_tool || ref.source }}
        </div>
      </div>
      <button
        v-if="canOpenEvidenceReference(ref)"
        type="button"
        class="evidence-card__action"
        :disabled="openingKey === evidenceReferenceKey(ref, index)"
        @click="openReference(ref, index)"
      >
        {{ openingKey === evidenceReferenceKey(ref, index) ? '打开中' : '打开' }}
      </button>
      <span
        v-else
        class="evidence-card__reason"
        :title="evidenceReferenceOpenReason(ref)"
      >
        暂不可直接打开
      </span>
    </article>
    <p v-if="openError" class="evidence-list__error">{{ openError }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiFetchRaw } from '../api'
import {
  canOpenEvidenceReference,
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

async function openReference(ref: EvidenceReference, index: number) {
  const fileId = numericFileId(ref)
  if (fileId === null) {
    openError.value = evidenceReferenceOpenReason(ref)
    return
  }
  const key = evidenceReferenceKey(ref, index)
  openingKey.value = key
  openError.value = ''
  try {
    const response = await apiFetchRaw(`/files/download/${fileId}`)
    if (!response.ok) throw new Error(`文件下载接口返回 ${response.status}`)
    const blob = await response.blob()
    const objectUrl = URL.createObjectURL(blob)
    window.open(objectUrl, '_blank', 'noopener')
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60_000)
  } catch (error: unknown) {
    openError.value = error instanceof Error ? error.message : '打开文件失败'
  } finally {
    openingKey.value = ''
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
  display: flex;
  flex-direction: column;
  gap: 2px;
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
.evidence-card__action {
  flex-shrink: 0;
  height: 24px;
  padding: 0 8px;
  border: 1px solid var(--ag-primary);
  border-radius: var(--ag-radius-sm);
  background: var(--ag-bg-base);
  color: var(--ag-primary);
  cursor: pointer;
  font-size: var(--ag-font-size-xs);
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
</style>
