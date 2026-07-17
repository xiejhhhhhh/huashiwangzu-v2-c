<template>
  <Teleport to="body">
    <div v-if="visible" ref="menuRef" class="v40-ctx-menu" role="menu" :style="{ left: x + 'px', top: y + 'px' }" @contextmenu.prevent @keydown="handleKeydown" @mouseenter="keepSubmenuOpen()" @mouseleave="closeSubmenu()">
      <template v-for="(item, index) in visibleMenuItems" :key="item.key">
        <div v-if="item.separator" class="v40-ctx-sep" role="separator" />
        <button v-else class="v40-ctx-item" :class="{ 'is-disabled': item.disabled, 'is-danger': item.danger, 'has-children': item.children, 'is-open': activeSubmenu?.parentKey === item.key }" type="button" role="menuitem" :disabled="item.disabled" :tabindex="index === firstActionIndex ? 0 : -1" @click.stop="item.children ? openSubmenu($event, item.key, item.children) : handleSelect(item)" @mouseenter="item.children ? openSubmenu($event, item.key, item.children) : closeSubmenu()">
          <span class="v40-ctx-check" aria-hidden="true" />
          <span class="v40-ctx-label">{{ item.label }}</span>
          <ChevronRight v-if="item.children" :size="14" />
        </button>
      </template>
    </div>
    <div v-if="activeSubmenu" class="v40-ctx-sub" role="menu" :style="{ left: activeSubmenu.x + 'px', top: activeSubmenu.y + 'px' }" @click.stop @keydown="handleKeydown" @mouseenter="keepSubmenuOpen()" @mouseleave="closeSubmenu()">
      <template v-for="child in activeSubmenu.items" :key="child.key">
        <div v-if="child.separator" class="v40-ctx-sep" role="separator" />
        <button v-else class="v40-ctx-item" :class="{ 'is-disabled': child.disabled, 'is-danger': child.danger }" type="button" role="menuitem" :disabled="child.disabled" tabindex="-1" @click.stop="handleSelect(child)">
          <span class="v40-ctx-check" aria-hidden="true" />
          <span class="v40-ctx-label">{{ child.label }}</span>
        </button>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ChevronRight } from 'lucide-vue-next'
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

const emit = defineEmits<{ select: [key: string]; dismiss: [] }>()
const menuRef = ref<HTMLElement | null>(null)
const visibleMenuItems = computed(() => props.currentItems.filter((item, i, list) => !item.separator || (i > 0 && i < list.length - 1 && !list[i - 1].separator && !list[i + 1].separator)))
const firstActionIndex = computed(() => visibleMenuItems.value.findIndex(item => !item.separator && !item.disabled))

watch(() => props.visible, visible => {
  if (visible) nextTick(() => menuRef.value?.querySelector<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')?.focus())
})

function handleSelect(item: MenuItemConfig) { if (!item.disabled && !item.children) emit('select', item.key) }
function handleKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); emit('dismiss'); return }
  const root = (event.currentTarget as HTMLElement)
  const items = [...root.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not(:disabled)')]
  const current = items.indexOf(document.activeElement as HTMLButtonElement)
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    const delta = event.key === 'ArrowDown' ? 1 : -1
    items[(current + delta + items.length) % items.length]?.focus()
  } else if (event.key === 'ArrowLeft' && props.activeSubmenu) {
    event.preventDefault(); props.closeSubmenu(); menuRef.value?.querySelector<HTMLButtonElement>('.is-open')?.focus()
  }
}
</script>

<style scoped>
.v40-ctx-menu,.v40-ctx-sub{position:fixed;z-index:var(--context-menu-z-index);min-width:var(--context-menu-min-width);padding:5px;border:1px solid var(--context-menu-border);border-radius:var(--context-menu-radius);background:var(--context-menu-bg);box-shadow:var(--context-menu-shadow);backdrop-filter:blur(var(--context-menu-blur)) saturate(160%);-webkit-backdrop-filter:blur(var(--context-menu-blur)) saturate(160%);color:var(--context-menu-text)}.v40-ctx-sub{z-index:calc(var(--context-menu-z-index) + 1)}
.v40-ctx-item{width:100%;height:28px;padding:0 8px;border:0;border-radius:6px;background:transparent;color:inherit;display:grid;grid-template-columns:14px minmax(0,1fr) 14px;align-items:center;gap:6px;text-align:left;font:var(--desktop-font-menu);cursor:default}.v40-ctx-item:hover:not(:disabled),.v40-ctx-item:focus-visible,.v40-ctx-item.is-open{background:var(--context-menu-hover-bg);color:white;outline:none}.v40-ctx-item.is-danger{color:var(--context-menu-danger-text)}.v40-ctx-item.is-danger:hover:not(:disabled),.v40-ctx-item.is-danger:focus-visible{background:#ff3b30;color:white}.v40-ctx-item:disabled{color:var(--context-menu-disabled-text)}.v40-ctx-sep{height:1px;margin:4px 7px;background:var(--context-menu-divider)}.v40-ctx-check{width:14px}.v40-ctx-label{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
@media(prefers-reduced-transparency:reduce){.v40-ctx-menu,.v40-ctx-sub{background:#f4f4f6;backdrop-filter:none}}
</style>
