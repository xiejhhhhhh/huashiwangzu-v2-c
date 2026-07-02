<template>
  <div class="dp-container">
    <div class="dp-header"><h3>📄 草稿列表</h3></div>

    <div v-if="loading" class="dp-loading">加载中…</div>
    <div v-else-if="drafts.length === 0" class="dp-empty">还没有草稿，去创作一篇吧</div>
    <div v-else class="dp-list">
      <div v-for="d in drafts" :key="d.id" class="dp-item">
        <div class="dp-item-main" @click="viewDraft(d)">
          <div class="dp-item-title">{{ d.title || '无标题' }}</div>
          <div class="dp-item-meta">
            <span class="dp-tag" :class="d.status === 'published' ? 'tag-success' : 'tag-info'">
              {{ d.status === 'published' ? '已发布' : '草稿' }}
            </span>
            <span>{{ formatDate(d.updated_at) }}</span>
            <span>v{{ d.version }}</span>
          </div>
        </div>
        <div class="dp-item-actions">
          <button class="dp-btn" @click="editDraft(d)">编辑</button>
          <button class="dp-btn dp-btn-danger" @click="deleteDraft(d)">删除</button>
        </div>
      </div>
    </div>

    <!-- View dialog -->
    <div v-if="viewDialog" class="dp-overlay" @click.self="viewDialog = false">
      <div class="dp-dialog">
        <div class="dp-dialog-header">
          <h3>{{ currentDraft?.title || '草稿详情' }}</h3>
          <button class="dp-close" @click="viewDialog = false">✕</button>
        </div>
        <div class="dp-dialog-body">
          <div class="dp-view-meta">
            <span class="dp-tag" :class="currentDraft?.status === 'published' ? 'tag-success' : 'tag-info'">
              {{ currentDraft?.status === 'published' ? '已发布' : '草稿' }}
            </span>
            <span>版本: {{ currentDraft?.version }}</span>
            <span>更新: {{ formatDate(currentDraft?.updated_at) }}</span>
          </div>
          <textarea v-model="currentDraft.content" class="dp-view-content" rows="20"></textarea>
        </div>
        <div class="dp-dialog-footer">
          <button class="dp-btn" @click="viewDialog = false">关闭</button>
          <button class="dp-btn dp-btn-primary" @click="copyDraft" v-if="currentDraft">复制全文</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiDelete, apiGet } from '../runtime'

interface Draft {
  id: number
  title?: string
  content?: string
  status?: string
  version?: number
  updated_at?: string
}

const emit = defineEmits<{ 'edit-draft': [draft: Draft] }>()
const loading = ref(false)
const drafts = ref<Draft[]>([])
const viewDialog = ref(false)
const currentDraft = ref<Draft>({ id: 0, content: '' })

onMounted(() => loadDrafts())

function toast(msg: string, type: 'success' | 'error' | 'warning' = 'success') {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:6px;z-index:9999;font-size:14px;'
  el.style.background = type === 'success' ? '#67c23a' : type === 'error' ? '#f56c6c' : '#e6a23c'
  el.style.color = '#fff'
  el.textContent = msg
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

async function loadDrafts() {
  loading.value = true
  try {
    const data = await apiGet<{ items?: Draft[] }>('/wechat-writer/drafts?page=1&page_size=50')
    drafts.value = data.items || []
  } catch (e: unknown) {
    console.error('Load drafts error:', e)
    toast(e instanceof Error ? e.message : '草稿加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function viewDraft(d: Draft) {
  currentDraft.value = { ...d }
  viewDialog.value = true
}

function editDraft(d: Draft) {
  emit('edit-draft', d)
}

async function deleteDraft(d: Draft) {
  if (!window.confirm('确定删除这篇草稿？')) return
  try {
    await apiDelete('/wechat-writer/drafts/' + d.id)
    toast('已删除', 'success')
    loadDrafts()
  } catch (e: unknown) {
    toast(e instanceof Error ? e.message : '删除失败', 'error')
  }
}

async function copyDraft() {
  if (!currentDraft.value?.content) return
  try {
    await navigator.clipboard.writeText(currentDraft.value.content)
    toast('已复制', 'success')
  } catch {
    toast('复制失败', 'warning')
  }
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return ''
  const d = new Date(dateStr)
  return d.toLocaleDateString('zh-CN') + ' ' + d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.dp-container { padding: 20px; }
.dp-header { margin-bottom: 16px; }
.dp-header h3 { margin: 0; font-size: 18px; color: #303133; }
.dp-loading { padding: 20px; color: #909399; }
.dp-empty { text-align: center; padding: 60px 0; color: #909399; }
.dp-list { display: flex; flex-direction: column; gap: 8px; }
.dp-item { display: flex; align-items: center; gap: 16px; padding: 12px 16px; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; }
.dp-item-main { flex: 1; cursor: pointer; }
.dp-item-main:hover .dp-item-title { color: #409eff; }
.dp-item-title { font-weight: 600; color: #303133; }
.dp-item-meta { display: flex; align-items: center; gap: 12px; margin-top: 4px; color: #909399; font-size: 12px; }
.dp-item-actions { flex-shrink: 0; display: flex; gap: 4px; }
.dp-tag { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.tag-success { background: #f0f9eb; color: #67c23a; }
.tag-info { background: #f4f4f5; color: #909399; }
.dp-btn { padding: 4px 12px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; cursor: pointer; font-size: 12px; }
.dp-btn:hover { border-color: #409eff; color: #409eff; }
.dp-btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.dp-btn-primary:hover { background: #66b1ff; }
.dp-btn-danger { color: #f56c6c; border-color: #f56c6c; }
.dp-btn-danger:hover { background: #fef0f0; }
.dp-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.dp-dialog { width: 80%; max-width: 900px; max-height: 85vh; background: #fff; border-radius: 8px; display: flex; flex-direction: column; }
.dp-dialog-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e4e7ed; }
.dp-dialog-header h3 { margin: 0; font-size: 16px; }
.dp-close { border: none; background: none; font-size: 18px; cursor: pointer; color: #909399; }
.dp-dialog-body { flex: 1; padding: 16px 20px; overflow: auto; }
.dp-view-meta { display: flex; gap: 12px; margin-bottom: 12px; align-items: center; color: #909399; font-size: 13px; }
.dp-view-content { width: 100%; padding: 10px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 14px; line-height: 1.8; font-family: inherit; box-sizing: border-box; }
.dp-dialog-footer { padding: 12px 20px; border-top: 1px solid #e4e7ed; display: flex; gap: 8px; justify-content: flex-end; }
</style>
