<template>
  <Teleport to="body">
    <div v-if="visible" class="v40-ctx-menu" :style="{ left: x + 'px', top: y + 'px' }" @contextmenu.prevent @mouseenter="keepSubmenuOpen()" @mouseleave="closeSubmenu()">
      <template v-for="item in visibleMenuItems" :key="item.key">
        <div v-if="item.separator" class="v40-ctx-sep" />
        <div v-else class="v40-ctx-item" :class="{ 'is-disabled': item.disabled, 'is-danger': item.danger, 'has-children': item.children, 'is-open': activeSubmenu?.parentKey === item.key }"
          @click.stop="item.children ? openSubmenu($event, item.key, item.children) : handleSelect(item)"
          @mouseenter="item.children ? openSubmenu($event, item.key, item.children) : closeSubmenu()">
          <span v-if="item.icon" class="v40-ctx-icon">{{ item.icon }}</span>
          <span class="v40-ctx-label">{{ item.label }}</span>
          <span v-if="item.children" class="v40-ctx-arrow">›</span>
        </div>
      </template>
    </div>
    <div v-if="activeSubmenu" class="v40-ctx-sub" :style="{ left: activeSubmenu.x + 'px', top: activeSubmenu.y + 'px' }" @click.stop @mouseenter="keepSubmenuOpen()" @mouseleave="closeSubmenu()">
      <template v-for="child in activeSubmenu.items" :key="child.key">
        <div v-if="child.separator" class="v40-ctx-sep" />
        <div v-else class="v40-ctx-item" :class="{ 'is-disabled': child.disabled, 'is-danger': child.danger }" @click.stop="handleSelect(child)">
          <span v-if="child.icon" class="v40-ctx-icon">{{ child.icon }}</span>
          <span class="v40-ctx-label">{{ child.label }}</span>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MenuItemConfig } from './use-context-menu'

const props = defineProps<{
  visible: boolean
  x: number
  y: number
  contextType?: string | null
  currentItems: MenuItemConfig[]
  activeSubmenu: { parentKey: string; items: MenuItemConfig[]; x: number; y: number } | null
  openSubmenu: (e: MouseEvent, parentKey: string, items: MenuItemConfig[]) => void
  closeSubmenu: () => void
  keepSubmenuOpen: () => void
}>()

const emit = defineEmits<{ select: [key: string] }>()

const visibleMenuItems = computed(() => {
  const list = props.currentItems
  return list.filter((item, i) => !item.separator || (i > 0 && i < list.length - 1 && !list[i - 1].separator && !list[i + 1].separator))
})

function handleSelect(item: MenuItemConfig) {
  if (item.disabled || item.children) return
  emit('select', item.key)
}
</script>

<style scoped>
.v40-ctx-menu {
  position: fixed; z-index: 99999; min-width: 196px;
  background: rgba(249,250,252,0.98); backdrop-filter: blur(18px);
  border: 1px solid rgba(214,220,228,0.92); border-radius: 11px;
  box-shadow: 0 14px 38px rgba(15,23,42,0.16); padding: 4px;
}
.v40-ctx-item {
  display: flex; align-items: center; gap: 8px; min-height: 33px; padding: 6px 10px; cursor: pointer;
  font-size: 12px; color: #111827; user-select: none; position: relative; border-radius: 8px; transition: background .14s ease, transform .14s ease;
}
.v40-ctx-item:hover:not(.is-disabled),.v40-ctx-item.is-open:not(.is-disabled) { background: rgba(59,130,246,0.10); transform: translateX(1px); }
.v40-ctx-item.is-danger { color: #e53e3e; }
.v40-ctx-item.is-danger:hover:not(.is-disabled) { background: rgba(229,62,62,0.10); }
.v40-ctx-item.is-disabled { color: #bbb; cursor: not-allowed; }
.v40-ctx-sep { margin: 4px 4px; border-top: 1px solid rgba(203,213,225,0.9); }
.v40-ctx-icon { font-size: 13px; width: 16px; text-align: center; }
.v40-ctx-label { flex: 1; }
.v40-ctx-arrow { margin-left: 8px; font-size: 16px; color: #94a3b8; }.v40-ctx-item.has-children .v40-ctx-arrow{color:#64748b}
.v40-ctx-sub {
  position: fixed; z-index: 100000; min-width: 192px;
  background: rgba(249,250,252,0.98); backdrop-filter: blur(16px);
  border: 1px solid rgba(214,220,228,0.92); border-radius: 11px;
  box-shadow: 0 14px 38px rgba(15,23,42,0.16); padding: 4px;
}
</style>
