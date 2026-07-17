<template>
  <div class="office-shell">
    <header class="office-chrome">
      <div>
        <h1>Office</h1>
        <p class="hint">统一文档工作区 · Product Runtime（WP5/WP6）</p>
      </div>
      <div class="actions">
        <button type="button" class="btn primary" :disabled="creating" @click="createDraft('docx')">新建 Word</button>
        <button type="button" class="btn" :disabled="creating" @click="createDraft('pptx')">新建演示</button>
        <button type="button" class="btn" :disabled="creating" @click="createDraft('xlsx')">新建表格</button>
        <button type="button" class="btn ghost" :disabled="loading" @click="loadHome">刷新</button>
      </div>
    </header>

    <section v-if="hasOpenMeta" class="open-banner">
      <strong>已通过 Resolver / 会话打开</strong>
      <span>fileId={{ fileId ?? '—' }}</span>
      <span>packageId={{ packageId ?? '—' }}</span>
      <span>mode={{ mode || 'view' }}</span>
      <span v-if="adapterId">adapter={{ adapterId }}</span>
    </section>

    <main class="office-body">
      <section class="card">
        <h2>最近内容包</h2>
        <p v-if="loading" class="muted">加载中…</p>
        <p v-else-if="!recent.length" class="muted">暂无最近项。点上方「新建」创建草稿（不产生桌面文件）。</p>
        <ul v-else class="recent-list">
          <li v-for="item in recent" :key="String(item.packageId)" class="recent-item">
            <div class="meta">
              <div class="title">{{ itemTitle(item) }}</div>
              <div class="sub">
                #{{ item.packageId }} · {{ item.profile || 'document' }} · {{ item.status }}
                <template v-if="item.sourceFileId"> · file {{ item.sourceFileId }}</template>
                <template v-else> · 草稿（无 File）</template>
              </div>
            </div>
            <button type="button" class="btn small" @click="openPackage(item)">打开</button>
          </li>
        </ul>
      </section>

      <section v-if="activePackage" class="card">
        <h2>当前会话</h2>
        <p class="muted">package #{{ activePackage.packageId }} · version #{{ activePackage.versionId }}</p>
        <div class="actions">
          <button type="button" class="btn" :disabled="saving" @click="autosave">自动保存版本</button>
          <button type="button" class="btn" :disabled="locking" @click="takeLock">获取编辑租约</button>
          <button type="button" class="btn" :disabled="exporting" @click="doExport">导出</button>
          <button type="button" class="btn" :disabled="publishing" @click="doPublish">发布投影</button>
        </div>
        <p v-if="statusText" class="status">{{ statusText }}</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  acquireContentLock,
  createContentDraft,
  exportContentPackage,
  fetchOfficeHome,
  publishContentPackage,
  saveContentPackage,
} from '@/shared/api/content-runtime'

// 窗口框架用 v-bind="payload" 直接摊平 props
const props = defineProps<{
  fileId?: number
  fileName?: string
  format?: string
  mode?: string
  packageId?: number
  versionId?: number
  resolutionId?: string
  adapterId?: string
  readonlyReason?: string
  productId?: string
  page?: number
}>()

const loading = ref(false)
const creating = ref(false)
const saving = ref(false)
const locking = ref(false)
const exporting = ref(false)
const publishing = ref(false)
const recent = ref<Array<Record<string, unknown>>>([])
const statusText = ref('')
const activePackage = ref<{ packageId: number; versionId: number; lockToken?: string } | null>(null)

const hasOpenMeta = computed(() => Boolean(props.fileId || props.packageId || props.resolutionId))

function itemTitle(item: Record<string, unknown>) {
  const raw = String(item.title || '')
  if (raw.startsWith('{')) {
    try {
      const parsed = JSON.parse(raw) as { title?: string }
      if (parsed.title) return parsed.title
    } catch {
      // fallthrough
    }
  }
  return raw || `Package #${item.packageId}`
}

async function loadHome() {
  loading.value = true
  try {
    const data = await fetchOfficeHome()
    recent.value = Array.isArray(data.recent) ? data.recent as Array<Record<string, unknown>> : []
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '加载 Office 首页失败')
  } finally {
    loading.value = false
  }
}

async function createDraft(extension: string) {
  creating.value = true
  try {
    const draft = await createContentDraft({
      productId: 'office',
      extension,
      title: `未命名.${extension}`,
      contentType: 'document',
    })
    activePackage.value = {
      packageId: Number(draft.packageId),
      versionId: Number(draft.versionId),
    }
    statusText.value = `已建草稿 package=${draft.packageId}（fileId=null）`
    ElMessage.success('草稿已创建（不产生桌面文件）')
    await loadHome()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '创建草稿失败')
  } finally {
    creating.value = false
  }
}

function openPackage(item: Record<string, unknown>) {
  activePackage.value = {
    packageId: Number(item.packageId),
    versionId: Number(item.currentVersionId || 0),
  }
  statusText.value = `已选 package=${item.packageId}`
}

async function autosave() {
  if (!activePackage.value?.packageId) return
  saving.value = true
  try {
    const result = await saveContentPackage(activePackage.value.packageId, {
      expectedVersionId: activePackage.value.versionId || null,
      autosave: true,
      summary: 'office-ui-autosave',
      lockToken: activePackage.value.lockToken || null,
    })
    activePackage.value = {
      ...activePackage.value,
      versionId: Number(result.versionId || activePackage.value.versionId),
    }
    statusText.value = `已自动保存 version=${result.versionId}`
    ElMessage.success('已新增版本（未物化 File）')
    await loadHome()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  } finally {
    saving.value = false
  }
}

async function takeLock() {
  if (!activePackage.value?.packageId) return
  locking.value = true
  try {
    const lease = await acquireContentLock(activePackage.value.packageId, {
      baseVersionId: activePackage.value.versionId,
      ttlSeconds: 300,
    })
    activePackage.value = {
      ...activePackage.value,
      lockToken: String(lease.token || ''),
    }
    statusText.value = `租约已获取，过期 ${lease.expiresAt || ''}`
    ElMessage.success('编辑租约已获取')
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '获取租约失败')
  } finally {
    locking.value = false
  }
}

async function doExport() {
  if (!activePackage.value?.packageId) return
  exporting.value = true
  try {
    const result = await exportContentPackage(activePackage.value.packageId)
    statusText.value = `已导出 file=${result.file_id || result.fileId} name=${result.file_name || result.fileName || ''}`
    ElMessage.success('导出完成')
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    exporting.value = false
  }
}

async function doPublish() {
  if (!activePackage.value?.packageId) return
  publishing.value = true
  try {
    const result = await publishContentPackage(activePackage.value.packageId)
    statusText.value = `已发布 artifact/file=${JSON.stringify(result).slice(0, 120)}`
    ElMessage.success('发布完成')
    await loadHome()
  } catch (e: unknown) {
    ElMessage.error(e instanceof Error ? e.message : '发布失败')
  } finally {
    publishing.value = false
  }
}

onMounted(() => {
  void loadHome()
  if (props.packageId) {
    activePackage.value = {
      packageId: Number(props.packageId),
      versionId: Number(props.versionId || 0),
    }
  }
})
</script>

<style scoped>
.office-shell { display:flex; flex-direction:column; height:100%; background:#f5f7fa; color:#1f2329; }
.office-chrome {
  display:flex; justify-content:space-between; gap:12px; align-items:flex-start;
  padding:14px 16px; background:#fff; border-bottom:1px solid #e5e7eb;
}
.office-chrome h1 { margin:0; font-size:18px; font-weight:650; }
.hint { margin:4px 0 0; font-size:12px; color:#6b7280; }
.actions { display:flex; flex-wrap:wrap; gap:8px; }
.btn {
  border:1px solid #d1d5db; background:#fff; border-radius:8px; padding:6px 10px;
  font-size:12px; cursor:pointer;
}
.btn:hover { background:#f9fafb; }
.btn.primary { background:#2563eb; border-color:#2563eb; color:#fff; }
.btn.primary:hover { background:#1d4ed8; }
.btn.ghost { background:transparent; }
.btn.small { padding:4px 8px; }
.btn:disabled { opacity:.55; cursor:not-allowed; }
.open-banner {
  display:flex; flex-wrap:wrap; gap:10px; padding:8px 16px; background:#eff6ff; color:#1e3a8a; font-size:12px;
  border-bottom:1px solid #bfdbfe;
}
.office-body { flex:1; overflow:auto; padding:16px; display:grid; gap:12px; }
.card { background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:14px 16px; }
.card h2 { margin:0 0 10px; font-size:14px; }
.muted { color:#6b7280; font-size:12px; }
.recent-list { list-style:none; margin:0; padding:0; display:grid; gap:8px; }
.recent-item {
  display:flex; justify-content:space-between; gap:12px; align-items:center;
  padding:10px 12px; border:1px solid #eef2f7; border-radius:10px; background:#fafbfc;
}
.title { font-size:13px; font-weight:600; }
.sub { font-size:11px; color:#6b7280; margin-top:2px; }
.status { margin-top:10px; font-size:12px; color:#065f46; }
</style>
