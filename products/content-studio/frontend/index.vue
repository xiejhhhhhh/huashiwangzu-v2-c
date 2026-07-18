<template>
  <div
    class="studio-app"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="document"
  >
    <MacAppShell layout="document">
      <template #toolbar>
        <div class="studio-toolbar">
          <div class="studio-toolbar-copy">
            <strong>内容工作室</strong>
            <span>Content Studio · Product Runtime</span>
          </div>
          <div class="studio-actions">
            <button type="button" class="mac-btn primary" :disabled="creating" @click="createDraft">新建 Markdown 草稿</button>
            <button type="button" class="mac-btn ghost" @click="openOffice">打开 Office</button>
          </div>
        </div>
      </template>

      <div class="studio-body">
        <section class="card">
          <h2>创作入口</h2>
          <p class="muted">本产品只编排内容创作会话，读写走 Content Runtime，不接物理路径。</p>
          <ul class="list">
            <li>新建草稿 → source-less Package（fileId=null）</li>
            <li>打开已有包 → 走 Resolver / Office 会话</li>
            <li>发布/物化 File 仍属后续切片（不假绿）</li>
          </ul>
        </section>
        <section v-if="statusText" class="card status">{{ statusText }}</section>
      </div>
    </MacAppShell>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { MacAppShell, useAppFeedback } from '@/desktop/app-kit'
import { createContentDraft } from '@/shared/api/content-runtime'
import { openAppById } from '@/desktop/app-registry/app-opener'

const feedback = useAppFeedback()
const creating = ref(false)
const statusText = ref('')

async function createDraft() {
  creating.value = true
  try {
    const draft = await createContentDraft({
      productId: 'content-studio',
      extension: 'md',
      title: '内容草稿.md',
      contentType: 'text',
    })
    statusText.value = `草稿已创建 package=${draft.packageId} version=${draft.versionId}（无 File）`
    feedback.success('内容草稿已创建')
    openAppById('office', {
      packageId: draft.packageId,
      versionId: draft.versionId,
      mode: 'edit',
      productId: 'content-studio',
    })
  } catch (e: unknown) {
    feedback.error(e instanceof Error ? e.message : '创建草稿失败')
  } finally {
    creating.value = false
  }
}

function openOffice() {
  openAppById('office', { productId: 'content-studio' })
}
</script>

<style scoped>
.studio-app {
  height: 100%;
  min-height: 0;
  color: var(--mac-app-text);
  background: var(--mac-app-surface);
}

.studio-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  width: 100%;
  min-height: var(--mac-app-toolbar-height);
  padding: 0 4px;
}

.studio-toolbar-copy {
  min-width: 0;
  display: grid;
  gap: 1px;
}

.studio-toolbar-copy strong {
  font: var(--mac-app-font-title);
  color: var(--mac-app-text);
}

.studio-toolbar-copy span {
  font: var(--mac-app-font-caption);
  color: var(--mac-app-text-secondary);
}

.studio-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.mac-btn {
  border: 1px solid var(--mac-app-border-strong);
  background: color-mix(in srgb, var(--mac-app-surface) 88%, white);
  border-radius: var(--mac-app-radius-control);
  padding: 6px 10px;
  font-size: 12px;
  color: var(--mac-app-text);
  cursor: pointer;
}

.mac-btn.primary {
  background: #7c3aed;
  border-color: #7c3aed;
  color: #fff;
}

.mac-btn.ghost {
  background: transparent;
}

.mac-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.studio-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 16px;
  display: grid;
  gap: 12px;
  box-sizing: border-box;
}

.card {
  background: color-mix(in srgb, var(--mac-app-surface) 70%, white);
  border: 1px solid var(--mac-app-border);
  border-radius: var(--mac-app-radius-card);
  padding: 14px 16px;
}

.card h2 {
  margin: 0 0 8px;
  font: var(--mac-app-font-title);
}

.muted {
  color: var(--mac-app-text-secondary);
  font-size: 12px;
}

.list {
  margin: 10px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--mac-app-text);
}

.status {
  font-size: 12px;
  color: #065f46;
}
</style>
