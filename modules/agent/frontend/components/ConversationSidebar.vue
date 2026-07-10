<template>
  <aside class="conv-sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <div class="sidebar-brand">
        <svg class="brand-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M12 2a10 10 0 0110 10c0 5.523-4.477 10-10 10a10 10 0 01-10-10c0-5.523 4.477-10 10-10z"/>
          <path d="M8 12h8M12 8v8"/>
        </svg>
        <span class="brand-text">AI 助手</span>
      </div>
      <button class="sidebar-toggle" @click="$emit('toggle')" :title="collapsed ? '展开侧栏' : '折叠侧栏'">
        <svg v-if="!collapsed" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
          <path d="M10 3L6 8l4 5"/>
        </svg>
        <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="16" height="16">
          <path d="M6 3l4 5-4 5"/>
        </svg>
      </button>
    </div>

    <div class="sidebar-actions">
      <button class="btn-workflow-panel" :class="{ active: adminActive === 'workflows' }" @click="$emit('admin', 'workflows')" title="工作流状态">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="14" height="14">
          <path d="M3 3h4v4H3zM9 3h4v4H9zM3 9h4v4H3zM9 9h4v4H9z"/>
          <path d="M7 5h2M5 7v2M11 7v2"/>
        </svg>
        <span>工作流</span>
      </button>
      <button v-if="isAdmin" class="btn-admin-panel" :class="{ active: adminActive === 'engine' }" @click="$emit('admin', 'engine')" title="引擎调优面板（仅管理员）">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="14" height="14">
          <path d="M2 12l6-10 6 10H2zM8 7v3M8 12v1"/>
        </svg>
        <span>引擎面板</span>
      </button>
      <button v-if="isAdmin" class="btn-admin-panel" :class="{ active: adminActive === 'config' }" @click="$emit('admin', 'config')" title="Agent 配置管理（仅管理员）">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="14" height="14">
          <rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/>
          <rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/>
        </svg>
        <span>Agent配置</span>
      </button>
      <button class="btn-new-conv" @click="$emit('new')" :disabled="loading">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
          <path d="M8 3v10M3 8h10"/>
        </svg>
        <span>新建对话</span>
      </button>
    </div>

    <nav class="conv-list" ref="listRef">
      <div
        v-for="c in conversations" :key="c.id"
        class="conv-item"
        :class="{ active: c.id === activeConvId }"
        @click="$emit('select', c.id)"
      >
        <div class="conv-content" @dblclick.stop="startEdit(c)">
          <svg class="conv-icon" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="14" height="14">
            <path d="M2 3h12v8H6l-4 3V3z"/>
          </svg>
          <input
            v-if="editingId === c.id"
            :ref="setEditInputRef(c.id)"
            v-model="editTitle"
            class="conv-title-edit"
            @keydown.enter="finishEdit(c)"
            @blur="finishEdit(c)"
            @click.stop
          />
          <span v-else class="conv-title">{{ c.title }}</span>
        </div>
        <div class="conv-actions" @click.stop>
          <button class="conv-act-btn" title="重命名" @click.stop="startEdit(c)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="12" height="12">
              <path d="M11.5 2.5l2 2L7 11H5V9l6.5-6.5z"/>
            </svg>
          </button>
          <button class="conv-act-btn danger" title="删除" @click.stop="$emit('delete', c)">
            <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.3" width="12" height="12">
              <path d="M3 4h10M6 4V3a1 1 0 011-1h2a1 1 0 011 1v1M5 4v9a1 1 0 001 1h4a1 1 0 001-1V4"/>
            </svg>
          </button>
        </div>
      </div>

      <div v-if="conversations.length === 0 && !loading" class="conv-empty">
        <svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="1" width="36" height="36" class="empty-icon">
          <rect x="4" y="8" width="40" height="28" rx="4"/>
          <path d="M16 36v4h16v-4"/>
        </svg>
        <p>暂无对话</p>
        <span class="empty-hint">点击上方按钮开始</span>
      </div>

      <div v-if="loading" class="conv-loading">
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
        <span class="loading-dot"></span>
      </div>
    </nav>
  </aside>

  <!-- 折叠后依然可见的展开手柄 -->
  <button
    v-if="collapsed"
    class="expand-handle"
    @click="$emit('toggle')"
    title="展开侧栏"
  >
    <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" width="14" height="14">
      <path d="M6 3l4 5-4 5"/>
    </svg>
  </button>
</template>

<script setup lang="ts">
import { ref, nextTick } from 'vue'
import type { ComponentPublicInstance } from 'vue'

const props = defineProps<{
  conversations: ConvItem[]
  activeConvId: number | null
  loading: boolean
  collapsed: boolean
  isAdmin?: boolean
  adminActive?: string
}>()

const emit = defineEmits<{
  select: [id: number]
  new: []
  rename: [item: ConvItem]
  delete: [item: ConvItem]
  toggle: []
  admin: [panel: string]
}>()

interface ConvItem { id: number; title: string; status?: string }

const editingId = ref<number | null>(null)
const editTitle = ref('')
const editInputRefs = new Map<number, HTMLInputElement>()

function setEditInputRef(id: number) {
  return (el: Element | ComponentPublicInstance | null) => {
    if (el instanceof HTMLInputElement) {
      editInputRefs.set(id, el)
    } else {
      editInputRefs.delete(id)
    }
  }
}

function startEdit(c: ConvItem) {
  editingId.value = c.id
  editTitle.value = c.title
  nextTick(() => editInputRefs.get(c.id)?.focus())
}

function finishEdit(c: ConvItem) {
  if (editingId.value !== c.id) return
  const newTitle = editTitle.value.trim()
  editingId.value = null
  if (newTitle && newTitle !== c.title) {
    emit('rename', { ...c, title: newTitle })
  }
}
</script>

<style scoped>
.conv-sidebar {
  width: 260px;
  min-width: 260px;
  background: var(--ag-bg-sidebar);
  border-right: 1px solid var(--ag-border-light);
  display: flex;
  flex-direction: column;
  transition: width var(--ag-transition-base), min-width var(--ag-transition-base);
  overflow: hidden;
}
.conv-sidebar.collapsed { width: 0; min-width: 0; }

/* 折叠后可见的展开手柄 */
.expand-handle {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 22px;
  height: 64px;
  border: 1px solid var(--ag-border-light);
  border-left: none;
  border-radius: 0 8px 8px 0;
  background: var(--ag-bg-base);
  color: var(--ag-text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 50;
  box-shadow: 1px 0 6px rgba(0,0,0,0.06);
  transition: all var(--ag-transition-fast);
}
.expand-handle:hover {
  color: var(--ag-primary);
  background: var(--ag-primary-light);
  border-color: var(--ag-primary);
  box-shadow: 1px 0 10px rgba(0,134,168,0.12);
}

/* Header */
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--ag-space-lg) var(--ag-space-lg);
  border-bottom: 1px solid var(--ag-border-light);
  flex-shrink: 0;
}
.sidebar-brand { display: flex; align-items: center; gap: var(--ag-space-sm); }
.brand-icon { width: 20px; height: 20px; color: var(--ag-primary); }
.brand-text { font-size: var(--ag-font-size-lg); font-weight: 600; color: var(--ag-text-primary); }
.sidebar-toggle {
  border: none; background: none; cursor: pointer; color: var(--ag-text-tertiary);
  padding: var(--ag-space-xs); border-radius: var(--ag-radius-sm);
  display: flex; align-items: center; justify-content: center;
  transition: color var(--ag-transition-fast), background var(--ag-transition-fast);
}
.sidebar-toggle:hover { color: var(--ag-text-secondary); background: var(--ag-bg-hover); }

/* Actions */
.sidebar-actions { padding: var(--ag-space-md) var(--ag-space-lg); flex-shrink: 0; }
.btn-new-conv {
  display: flex; align-items: center; gap: var(--ag-space-sm);
  width: 100%; padding: var(--ag-space-sm) var(--ag-space-md);
  border: 1px dashed var(--ag-border-base); border-radius: var(--ag-radius-md);
  background: var(--ag-bg-base); color: var(--ag-primary);
  cursor: pointer; font-size: var(--ag-font-size-base);
  transition: all var(--ag-transition-fast);
}
.btn-new-conv:hover { background: var(--ag-primary-light); border-color: var(--ag-primary); }
.btn-new-conv:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-admin-panel,
.btn-workflow-panel {
  display: flex; align-items: center; gap: var(--ag-space-sm);
  width: 100%; padding: var(--ag-space-sm) var(--ag-space-md);
  margin-bottom: var(--ag-space-sm);
  border: 1px solid var(--ag-border-base); border-radius: var(--ag-radius-md);
  background: var(--ag-bg-base); color: var(--ag-text-secondary);
  cursor: pointer; font-size: var(--ag-font-size-base);
  transition: all var(--ag-transition-fast);
}
.btn-admin-panel:hover,
.btn-workflow-panel:hover { background: var(--ag-primary-light); border-color: var(--ag-primary); color: var(--ag-primary); }
.btn-admin-panel.active,
.btn-workflow-panel.active { background: var(--ag-primary-light); border-color: var(--ag-primary); color: var(--ag-primary); font-weight: 500; }

/* List */
.conv-list { flex: 1; overflow-y: auto; padding: 0 var(--ag-space-sm) var(--ag-space-sm); }
.conv-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: var(--ag-space-sm) var(--ag-space-md);
  margin: 1px 0;
  border-radius: var(--ag-radius-md);
  cursor: pointer; transition: background var(--ag-transition-fast);
}
.conv-item:hover { background: var(--ag-bg-hover); }
.conv-item.active { background: var(--ag-primary-light); }
.conv-content { display: flex; align-items: center; gap: var(--ag-space-sm); min-width: 0; flex: 1; }
.conv-icon { flex-shrink: 0; color: var(--ag-text-tertiary); }
.conv-item.active .conv-icon { color: var(--ag-primary); }
.conv-title {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-size: var(--ag-font-size-base); color: var(--ag-text-primary);
}
.conv-item.active .conv-title { color: var(--ag-primary); font-weight: 500; }

.conv-title-edit {
  flex: 1; min-width: 0;
  border: 1px solid var(--ag-primary);
  border-radius: var(--ag-radius-sm);
  padding: 2px 6px;
  font-size: var(--ag-font-size-base);
  font-family: inherit;
  color: var(--ag-text-primary);
  background: var(--ag-bg-base);
  outline: none;
}

.conv-actions {
  display: none; gap: 2px; flex-shrink: 0; margin-left: var(--ag-space-sm);
}
.conv-item:hover .conv-actions { display: flex; }
.conv-act-btn {
  border: none; background: none; cursor: pointer;
  padding: 3px; border-radius: var(--ag-radius-sm);
  color: var(--ag-text-tertiary); transition: all var(--ag-transition-fast);
}
.conv-act-btn:hover { background: var(--ag-bg-hover); color: var(--ag-text-secondary); }
.conv-act-btn.danger:hover { color: var(--ag-error); background: #FFF0F0; }

/* Empty state */
.conv-empty {
  display: flex; flex-direction: column; align-items: center;
  padding: var(--ag-space-3xl) var(--ag-space-lg); color: var(--ag-text-tertiary);
}
.empty-icon { margin-bottom: var(--ag-space-md); opacity: 0.4; }
.conv-empty p { margin: 0; font-size: var(--ag-font-size-md); }
.empty-hint { font-size: var(--ag-font-size-sm); margin-top: var(--ag-space-xs); }

/* Loading */
.conv-loading {
  display: flex; justify-content: center; gap: 4px;
  padding: var(--ag-space-2xl);
}
.loading-dot {
  width: 6px; height: 6px; border-radius: var(--ag-radius-full);
  background: var(--ag-text-tertiary); animation: dotPulse 1.2s ease-in-out infinite;
}
.loading-dot:nth-child(2) { animation-delay: 0.2s; }
.loading-dot:nth-child(3) { animation-delay: 0.4s; }
@keyframes dotPulse { 0%, 100% { opacity: 0.3; } 50% { opacity: 1; } }
</style>
