<template>
  <aside class="conv-sidebar" :class="{ collapsed }">
    <div class="sidebar-header">
      <span class="brand-text">AI 助手</span>
      <button class="sidebar-toggle" @click="$emit('toggle')" title="折叠侧栏" aria-label="折叠侧栏">
        <PanelLeftClose :size="16" />
      </button>
    </div>

    <div class="sidebar-actions">
      <button class="btn-new-conv" @click="$emit('new')" :disabled="loading">
        <SquarePen :size="15" />
        <span>新建对话</span>
      </button>
      <label class="conversation-search">
        <Search :size="13" />
        <input v-model="query" type="search" placeholder="搜索对话" aria-label="搜索对话" />
      </label>
    </div>

    <nav class="conv-list" ref="listRef">
      <p class="list-label">对话</p>
      <div
        v-for="c in filteredConversations" :key="c.id"
        class="conv-item"
        :class="{ active: c.id === activeConvId }"
        @click="$emit('select', c.id)"
      >
        <div class="conv-content" @dblclick.stop="startEdit(c)">
          <MessageCircle :size="14" class="conv-icon" />
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
            <Pencil :size="12" />
          </button>
          <button class="conv-act-btn danger" title="删除" @click.stop="$emit('delete', c)">
            <Trash2 :size="12" />
          </button>
        </div>
      </div>

      <div v-if="filteredConversations.length === 0 && !loading" class="conv-empty">
        <MessageCircle :size="30" class="empty-icon" />
        <p>{{ query ? '没有匹配的对话' : '暂无对话' }}</p>
        <span class="empty-hint">{{ query ? '换个关键词试试' : '新建对话开始工作' }}</span>
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
    <PanelLeftOpen :size="15" />
  </button>
</template>

<script setup lang="ts">
import { computed, ref, nextTick } from 'vue'
import type { ComponentPublicInstance } from 'vue'
import { MessageCircle, PanelLeftClose, PanelLeftOpen, Pencil, Search, SquarePen, Trash2 } from '@/shared/icons/lucide'

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
const query = ref('')
const editInputRefs = new Map<number, HTMLInputElement>()
const filteredConversations = computed(() => {
  const keyword = query.value.trim().toLocaleLowerCase()
  if (!keyword) return props.conversations
  return props.conversations.filter(item => item.title.toLocaleLowerCase().includes(keyword))
})

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
  width: 100%;
  min-width: 0;
  height: 100%;
  background: transparent;
  border-right: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.conv-sidebar.collapsed { width: 0; min-width: 0; }

/* 折叠后可见的展开手柄 */
.expand-handle {
  position: absolute;
  left: 0;
  top: 50%;
  transform: translateY(-50%);
  width: 26px;
  height: 54px;
  border: 1px solid var(--ag-border-light);
  border-left: none;
  border-radius: 0 9px 9px 0;
  background: rgba(250, 250, 252, 0.92);
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
  height: 48px;
  padding: 0 12px 0 16px;
  flex-shrink: 0;
}
.brand-text { font-size: 14px; font-weight: 650; color: var(--ag-text-primary); }
.sidebar-toggle {
  border: none; background: none; cursor: pointer; color: var(--ag-text-tertiary);
  padding: var(--ag-space-xs); border-radius: var(--ag-radius-sm);
  display: flex; align-items: center; justify-content: center;
  transition: color var(--ag-transition-fast), background var(--ag-transition-fast);
}
.sidebar-toggle:hover { color: var(--ag-text-secondary); background: var(--ag-bg-hover); }

/* Actions */
.sidebar-actions { padding: 4px 10px 10px; flex-shrink: 0; display: grid; gap: 8px; }
.btn-new-conv {
  display: flex; align-items: center; gap: var(--ag-space-sm);
  width: 100%; height: 34px; padding: 0 10px;
  border: none; border-radius: 8px;
  background: rgba(255,255,255,0.72); color: #007aff;
  box-shadow: inset 0 0 0 0.5px rgba(60,60,67,.16);
  cursor: pointer; font-size: 12px; font-weight: 550;
  transition: all var(--ag-transition-fast);
}
.btn-new-conv:hover { background: rgba(0,122,255,.09); }
.btn-new-conv:disabled { opacity: 0.5; cursor: not-allowed; }
.conversation-search { height: 30px; display: flex; align-items: center; gap: 6px; padding: 0 9px; border-radius: 8px; color: #8e8e93; background: rgba(118,118,128,.12); }
.conversation-search input { width: 100%; min-width: 0; border: 0; outline: 0; background: transparent; font: inherit; font-size: 12px; color: var(--ag-text-primary); }
.conversation-search input::-webkit-search-cancel-button { display: none; }

/* List */
.conv-list { flex: 1; overflow-y: auto; padding: 0 8px 10px; }
.list-label { margin: 4px 8px 6px; color: #8e8e93; font-size: 10px; font-weight: 650; text-transform: uppercase; }
.conv-item {
  display: flex; align-items: center; justify-content: space-between;
  min-height: 38px; padding: 5px 8px;
  margin: 2px 0;
  border-radius: 8px;
  cursor: pointer; transition: background var(--ag-transition-fast);
}
.conv-item:hover { background: rgba(118,118,128,.10); }
.conv-item.active { background: #0a84ff; }
.conv-content { display: flex; align-items: center; gap: var(--ag-space-sm); min-width: 0; flex: 1; }
.conv-icon { flex-shrink: 0; color: var(--ag-text-tertiary); }
.conv-item.active .conv-icon { color: rgba(255,255,255,.9); }
.conv-title {
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  font-size: 12px; color: var(--ag-text-primary);
}
.conv-item.active .conv-title { color: #fff; font-weight: 550; }
.conv-item.active .conv-act-btn { color: rgba(255,255,255,.78); }
.conv-item.active .conv-act-btn:hover { color: #fff; background: rgba(255,255,255,.16); }

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
