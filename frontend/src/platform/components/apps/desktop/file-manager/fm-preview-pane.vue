<template>
  <aside class="fm-preview-pane" aria-label="预览">
    <template v-if="item">
      <div class="fm-preview-icon">
        <FileVisualIcon
          :kind="item.is_folder || !item.format ? 'folder' : 'file'"
          :extension="item.format || ''"
          :size="88"
        />
      </div>
      <div class="fm-preview-name">{{ displayName(item) }}</div>
      <div class="fm-preview-kind">
        {{ item.is_folder ? '文件夹' : ((item.format || '文件').toUpperCase()) }}
      </div>

      <dl class="fm-preview-meta">
        <div class="fm-preview-row">
          <dt>大小</dt>
          <dd>{{ item.is_folder ? '—' : formatSize(item.file_size) }}</dd>
        </div>
        <div class="fm-preview-row">
          <dt>创建</dt>
          <dd>{{ formatDate(item.created_at) }}</dd>
        </div>
        <div v-if="!item.is_folder && item.format" class="fm-preview-row">
          <dt>种类</dt>
          <dd>{{ item.format.toUpperCase() }} 文档</dd>
        </div>
      </dl>
    </template>
    <div v-else class="fm-preview-empty">
      <span>未选择项目</span>
      <small>选择文件或文件夹以查看信息</small>
    </div>
  </aside>
</template>

<script setup lang="ts">
import FileVisualIcon from '@/shared/components/file-visual-icon.vue'
import type { FileEntry } from '@/shared/api/types'

defineProps<{
  item: FileEntry | null
  displayName: (file: FileEntry) => string
  formatSize: (size: number) => string
}>()

function formatDate(raw?: string | null) {
  if (!raw) return '—'
  const d = new Date(raw)
  if (Number.isNaN(d.getTime())) return String(raw).slice(0, 16)
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const yesterday = new Date(now)
  yesterday.setDate(now.getDate() - 1)
  const time = d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  if (sameDay) return `今天 ${time}`
  if (d.toDateString() === yesterday.toDateString()) return `昨天 ${time}`
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<style scoped>
.fm-preview-pane {
  width: 220px;
  flex-shrink: 0;
  border-left: 0.5px solid rgba(60, 60, 67, 0.14);
  background: color-mix(in srgb, #f7f7f9 92%, white);
  padding: 20px 16px;
  box-sizing: border-box;
  overflow: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.fm-preview-icon {
  width: 120px;
  height: 100px;
  display: grid;
  place-items: center;
  margin-bottom: 12px;
}

.fm-preview-name {
  width: 100%;
  text-align: center;
  font: 600 13px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: #1d1d1f;
  word-break: break-word;
  margin-bottom: 4px;
}

.fm-preview-kind {
  font: 400 11px/1.3 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: rgba(60, 60, 67, 0.58);
  margin-bottom: 16px;
}

.fm-preview-meta {
  width: 100%;
  margin: 0;
  padding: 10px 0 0;
  border-top: 0.5px solid rgba(60, 60, 67, 0.12);
  display: grid;
  gap: 8px;
}

.fm-preview-row {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 8px;
  font: 400 11px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
}

.fm-preview-row dt {
  margin: 0;
  color: rgba(60, 60, 67, 0.55);
}

.fm-preview-row dd {
  margin: 0;
  color: #1d1d1f;
  text-align: right;
  word-break: break-word;
}

.fm-preview-empty {
  margin-top: 48px;
  display: grid;
  gap: 6px;
  justify-items: center;
  color: rgba(60, 60, 67, 0.48);
  text-align: center;
  font: 400 12px/1.4 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
}

.fm-preview-empty small {
  font-size: 11px;
  opacity: 0.85;
}
</style>
