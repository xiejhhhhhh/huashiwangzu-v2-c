<template>
  <div class="viewer-shell">
    <div class="vs-toolbar">
      <div class="vs-toolbar-left">
        <span class="vs-file-icon">{{ fileIcon }}</span>
        <span class="vs-file-name">{{ fileName || '未知文件' }}</span>
        <span class="vs-app-badge">{{ appName }}</span>
      </div>
      <div class="vs-toolbar-center">
        <slot name="toolbar-center" />
      </div>
      <div class="vs-toolbar-right">
        <slot name="toolbar-extra" />
        <button v-if="showZoomOut" class="vs-btn" title="缩小" @click="$emit('zoom-out')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </button>
        <button v-if="showZoomIn" class="vs-btn" title="放大" @click="$emit('zoom-in')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </button>
        <button v-if="showFit" class="vs-btn" title="适应窗口" @click="$emit('fit')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
        </button>
        <button v-if="showSave" class="vs-btn vs-btn-primary" title="保存" @click="$emit('save')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          <span>保存</span>
        </button>
        <button v-if="showDownload" class="vs-btn" title="下载" @click="$emit('download')">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          <span>下载</span>
        </button>
      </div>
    </div>
    <div class="vs-content">
      <slot />
    </div>
    <div v-if="$slots.statusbar" class="vs-statusbar">
      <slot name="statusbar" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  fileName: string
  appName: string
  fileIcon?: string
  showSave?: boolean
  showDownload?: boolean
  showZoomIn?: boolean
  showZoomOut?: boolean
  showFit?: boolean
}>()

defineEmits<{
  save: []
  download: []
  'zoom-in': []
  'zoom-out': []
  fit: []
}>()
</script>

<style scoped>
.viewer-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
  font-family: '苹方', 'Microsoft YaHei', '宋体', sans-serif;
  color: #333;
}

.vs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 12px;
  background: #fff;
  border-bottom: 1px solid #e0e0e0;
  min-height: 42px;
  flex-shrink: 0;
}

.vs-toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.vs-file-icon {
  font-size: 18px;
}

.vs-file-name {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 240px;
}

.vs-app-badge {
  font-size: 11px;
  color: #2395bc;
  background: #e8f4f9;
  padding: 1px 8px;
  border-radius: 3px;
  white-space: nowrap;
}

.vs-toolbar-center {
  display: flex;
  align-items: center;
  gap: 4px;
}

.vs-toolbar-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.vs-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border: 1px solid #d0d0d0;
  border-radius: 4px;
  background: #fff;
  color: #555;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  font-family: inherit;
  white-space: nowrap;
}

.vs-btn:hover {
  border-color: #2395bc;
  color: #2395bc;
  background: #f0f8fc;
}

.vs-btn-primary {
  background: #2395bc;
  border-color: #2395bc;
  color: #fff;
}

.vs-btn-primary:hover {
  background: #1a7a9e;
  border-color: #1a7a9e;
  color: #fff;
}

.vs-content {
  flex: 1;
  overflow: auto;
  position: relative;
}

.vs-statusbar {
  padding: 4px 12px;
  background: #fff;
  border-top: 1px solid #e0e0e0;
  font-size: 12px;
  color: #888;
  flex-shrink: 0;
}
</style>
