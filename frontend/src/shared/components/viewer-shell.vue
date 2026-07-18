<template>
  <div class="viewer-shell" data-mac-app-kit="mac-app-v1" data-mac-app-layout="document">
    <div class="vs-toolbar">
      <div class="vs-toolbar-left">
        <span class="vs-file-icon" aria-hidden="true">{{ fileIcon }}</span>
        <div class="vs-file-meta">
          <span class="vs-file-name">{{ fileName || '未知文件' }}</span>
          <span class="vs-app-badge">{{ appName }}</span>
        </div>
      </div>
      <div class="vs-toolbar-center">
        <slot name="toolbar-center" />
      </div>
      <div class="vs-toolbar-right">
        <slot name="toolbar-extra" />
        <button v-if="showZoomOut" type="button" class="vs-btn" title="缩小" @click="$emit('zoom-out')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </button>
        <button v-if="showZoomIn" type="button" class="vs-btn" title="放大" @click="$emit('zoom-in')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/><line x1="11" y1="8" x2="11" y2="14"/><line x1="8" y1="11" x2="14" y2="11"/></svg>
        </button>
        <button v-if="showFit" type="button" class="vs-btn" title="适应窗口" @click="$emit('fit')">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"/></svg>
        </button>
        <button v-if="showSave" type="button" class="vs-btn vs-btn-primary" title="保存" @click="$emit('save')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg>
          <span>保存</span>
        </button>
        <button v-if="showDownload" type="button" class="vs-btn" title="下载" @click="$emit('download')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
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
import '@/desktop/app-kit/tokens-app.css'

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
  min-height: 0;
  color: var(--mac-app-text, #1d1d1f);
  background: var(--mac-app-surface, #f5f5f7);
  font: var(
    --mac-app-font,
    400 13px/1.45 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif
  );
}

.vs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: var(--mac-app-toolbar-height, 44px);
  padding: 0 12px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.12));
  background: var(--mac-app-surface-toolbar, rgba(246, 246, 248, 0.86));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
  backdrop-filter: var(--desktop-lg-filter-soft, blur(22px) saturate(160%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(22px) saturate(160%));
}

.vs-toolbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  flex: 1;
}

.vs-file-icon {
  width: 28px;
  height: 28px;
  border-radius: 7px;
  display: grid;
  place-items: center;
  font-size: 15px;
  background: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 10%, white);
  border: 1px solid color-mix(in srgb, var(--mac-app-accent, #0a84ff) 18%, transparent);
  flex-shrink: 0;
}

.vs-file-meta {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.vs-file-name {
  font: 600 13px/1.25 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: var(--mac-app-text, #1d1d1f);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

.vs-app-badge {
  width: fit-content;
  font: 500 10px/1.2 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  color: var(--mac-app-text-secondary, #6e6e73);
  letter-spacing: 0.01em;
}

.vs-toolbar-center {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.vs-toolbar-right {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.vs-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.14));
  border-radius: 8px;
  background: color-mix(in srgb, white 78%, transparent);
  color: var(--mac-app-text, #1d1d1f);
  font: 500 12px/1 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.12s ease, border-color 0.12s ease, color 0.12s ease;
}

.vs-btn:hover {
  background: color-mix(in srgb, white 92%, transparent);
  border-color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 28%, var(--mac-app-border, rgba(60, 60, 67, 0.14)));
  color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 70%, #1d1d1f);
}

.vs-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.vs-btn-primary {
  background: var(--mac-app-accent, #0a84ff);
  border-color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 80%, #0040dd);
  color: #fff;
  box-shadow: 0 1px 2px rgba(10, 132, 255, 0.28);
}

.vs-btn-primary:hover {
  filter: brightness(1.04);
  color: #fff;
  border-color: color-mix(in srgb, var(--mac-app-accent, #0a84ff) 80%, #0040dd);
  background: var(--mac-app-accent, #0a84ff);
}

.vs-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  position: relative;
  background: var(--mac-app-surface, #fbfbfd);
}

.vs-statusbar {
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: var(--mac-app-statusbar-height, 26px);
  padding: 0 12px;
  flex-shrink: 0;
  border-top: 1px solid var(--mac-app-border, rgba(60, 60, 67, 0.1));
  background: var(--mac-app-surface-status, rgba(246, 246, 248, 0.92));
  color: var(--mac-app-text-secondary, #6e6e73);
  font: var(
    --mac-app-font-caption,
    400 11px/1.3 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif
  );
}
</style>
