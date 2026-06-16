<template>
  <Teleport to="body">
    <div v-if="显示" class="v40-ctx-menu" :style="{ left: X + 'px', top: Y + 'px' }" @contextmenu.prevent @mouseenter="保持子菜单展开()" @mouseleave="关闭子菜单()">
      <template v-for="项 in 可视菜单项" :key="项.键">
        <div v-if="项.分隔符" class="v40-ctx-sep" />
        <div v-else class="v40-ctx-item" :class="{ 'is-disabled': 项.禁用, 'is-danger': 项.危险, 'has-children': 项.子项, 'is-open': 活跃子菜单?.父键 === 项.键 }"
          @click.stop="项.子项 ? 展开子菜单($event, 项.键, 项.子项) : 处理选中(项)"
          @mouseenter="项.子项 ? 展开子菜单($event, 项.键, 项.子项) : 关闭子菜单()">
          <span v-if="项.图标" class="v40-ctx-icon">{{ 项.图标 }}</span>
          <span class="v40-ctx-label">{{ 项.标签 }}</span>
          <span v-if="项.子项" class="v40-ctx-arrow">›</span>
        </div>
      </template>
    </div>
    <div v-if="活跃子菜单" class="v40-ctx-sub" :style="{ left: 活跃子菜单.X + 'px', top: 活跃子菜单.Y + 'px' }" @click.stop @mouseenter="保持子菜单展开()" @mouseleave="关闭子菜单()">
      <template v-for="子 in 活跃子菜单.项" :key="子.键">
        <div v-if="子.分隔符" class="v40-ctx-sep" />
        <div v-else class="v40-ctx-item" :class="{ 'is-disabled': 子.禁用, 'is-danger': 子.危险 }" @click.stop="处理选中(子)">
          <span v-if="子.图标" class="v40-ctx-icon">{{ 子.图标 }}</span>
          <span class="v40-ctx-label">{{ 子.标签 }}</span>
        </div>
      </template>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MenuItemConfig } from './use-context-menu'

const props = defineProps<{
  显示: boolean
  X: number
  Y: number
  上下文类型?: string | null
  当前项: MenuItemConfig[]
  活跃子菜单: { 父键: string; 项: MenuItemConfig[]; X: number; Y: number } | null
  展开子菜单: (e: MouseEvent, 父键: string, 项: MenuItemConfig[]) => void
  关闭子菜单: () => void
  保持子菜单展开: () => void
}>()

const emit = defineEmits<{ select: [键: string] }>()

const 可视菜单项 = computed(() => {
  const 列表 = props.当前项
  return 列表.filter((项, i) => !项.分隔符 || (i > 0 && i < 列表.length - 1 && !列表[i - 1].分隔符 && !列表[i + 1].分隔符))
})

function 处理选中(项: MenuItemConfig) {
  if (项.禁用 || 项.子项) return
  emit('select', 项.键)
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
