<template>
  <div class="studio-shell">
    <header class="studio-chrome">
      <div>
        <h1>内容工作室</h1>
        <p class="hint">Content Studio · Product Runtime（WP5/WP6）</p>
      </div>
      <div class="actions">
        <button type="button" class="btn primary" :disabled="creating" @click="createDraft">新建 Markdown 草稿</button>
        <button type="button" class="btn ghost" @click="openOffice">打开 Office</button>
      </div>
    </header>
    <main class="studio-body">
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
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { ElMessage } from 'element-plus'
import { createContentDraft } from '@/shared/api/content-runtime'
import { openAppById } from '@/desktop/app-registry/app-opener'

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
    ElMessage.success('内容草稿已创建')
    openAppById('office', {
      packageId: draft.packageId,
      versionId: draft.versionId,
      mode: 'edit',
      productId: 'content-studio',
    })
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '创建草稿失败')
  } finally {
    creating.value = false
  }
}

function openOffice() {
  openAppById('office', { productId: 'content-studio' })
}
</script>

<style scoped>
.studio-shell { display:flex; flex-direction:column; height:100%; background:#f7f8fa; color:#1f2329; }
.studio-chrome {
  display:flex; justify-content:space-between; gap:12px; align-items:flex-start;
  padding:14px 16px; background:#fff; border-bottom:1px solid #e5e7eb;
}
.studio-chrome h1 { margin:0; font-size:18px; font-weight:650; }
.hint { margin:4px 0 0; font-size:12px; color:#6b7280; }
.actions { display:flex; gap:8px; flex-wrap:wrap; }
.btn {
  border:1px solid #d1d5db; background:#fff; border-radius:8px; padding:6px 10px;
  font-size:12px; cursor:pointer;
}
.btn.primary { background:#7c3aed; border-color:#7c3aed; color:#fff; }
.btn.ghost { background:transparent; }
.btn:disabled { opacity:.55; cursor:not-allowed; }
.studio-body { flex:1; overflow:auto; padding:16px; display:grid; gap:12px; }
.card { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:14px 16px; }
.card h2 { margin:0 0 8px; font-size:14px; }
.muted { color:#6b7280; font-size:12px; }
.list { margin:10px 0 0; padding-left:18px; font-size:12px; color:#374151; }
.status { font-size:12px; color:#065f46; }
</style>
