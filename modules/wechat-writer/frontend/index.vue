<template>
  <div class="ww-container">
    <div class="ww-sidebar">
      <div class="ww-menu">
        <div
          v-for="tab in tabs"
          :key="tab.key"
          class="ww-menu-item"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span class="ww-menu-icon">{{ tab.icon }}</span>
          <span>{{ tab.label }}</span>
        </div>
      </div>
    </div>
    <div class="ww-main">
      <GeneratePanel v-if="activeTab === 'generate'" @save-draft="onSaveDraft" />
      <DraftsPanel v-else-if="activeTab === 'drafts'" @edit-draft="onEditDraft" />
      <PromptsPanel v-else-if="activeTab === 'prompts'" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import GeneratePanel from './generate-panel.vue'
import DraftsPanel from './drafts-panel.vue'
import PromptsPanel from './prompts-panel.vue'

const tabs = [
  { key: 'generate', label: '创作文章', icon: '✏️' },
  { key: 'drafts', label: '草稿箱', icon: '📄' },
  { key: 'prompts', label: '提示词管理', icon: '⚙️' },
]

const activeTab = ref('generate')

async function onSaveDraft(data: unknown) {
  return data
}

function onEditDraft(_draft: unknown) {
  activeTab.value = 'generate'
}
</script>

<style scoped>
.ww-container { display: flex; height: 100%; background: #f5f7fa; }
.ww-sidebar { width: 160px; background: #fff; border-right: 1px solid #e4e7ed; flex-shrink: 0; padding-top: 8px; }
.ww-menu-item { display: flex; align-items: center; gap: 8px; padding: 10px 20px; cursor: pointer; color: #606266; font-size: 14px; }
.ww-menu-item:hover { background: #ecf5ff; color: #409eff; }
.ww-menu-item.active { background: #ecf5ff; color: #409eff; font-weight: 600; }
.ww-menu-icon { font-size: 16px; }
.ww-main { flex: 1; display: flex; flex-direction: column; min-width: 0; overflow: auto; }
</style>
