<template>
  <div class="dashboard">
    <h2 class="db-title">知识库健康看板</h2>
    <div v-if="loadError" class="db-error" role="alert">
      <span>{{ loadError }}</span>
      <button type="button" @click="refreshStats">重试</button>
    </div>
    <div class="db-cards">
      <div class="db-card"><span class="db-num">{{ s.total_documents }}</span><span class="db-label">总文件数</span></div>
      <div class="db-card ok"><span class="db-num">{{ s.completed_documents }}</span><span class="db-label">深度完成</span></div>
      <div class="db-card warn"><span class="db-num">{{ s.partial_documents || 0 }}</span><span class="db-label">部分完成</span></div>
      <div class="db-card busy"><span class="db-num">{{ s.running_documents }}</span><span class="db-label">分析中</span></div>
      <div class="db-card queue"><span class="db-num">{{ s.queued_documents || 0 }}</span><span class="db-label">已入队</span></div>
      <div class="db-card pause"><span class="db-num">{{ s.paused_documents || 0 }}</span><span class="db-label">暂停中</span></div>
      <div class="db-card wait"><span class="db-num">{{ s.waiting_documents || 0 }}</span><span class="db-label">等待调度</span></div>
      <div class="db-card err"><span class="db-num">{{ s.failed_documents }}</span><span class="db-label">失败/卡住</span></div>
      <div class="db-card source"><span class="db-num">{{ s.source_unavailable_documents || 0 }}</span><span class="db-label">源文件不可用</span></div>
      <button class="db-card action-card" type="button" @click="showGovernance = !showGovernance">
        <span class="db-num">{{ pendingCount }}</span><span class="db-label">治理待办</span>
      </button>
      <div class="db-card"><span class="db-num">{{ s.total_entities }}</span><span class="db-label">实体总数</span></div>
      <div class="db-card"><span class="db-num">{{ s.total_graph_relations }}</span><span class="db-label">图谱关系</span></div>
      <div class="db-card"><span class="db-num">{{ s.total_file_relations }}</span><span class="db-label">跨文件关联</span></div>
      <div class="db-card warn"><span class="db-num">{{ s.duplicate_entity_count }}</span><span class="db-label">重复实体</span></div>
    </div>

    <section class="db-section">
      <h3>各文件分析进度</h3>
      <div class="db-table-wrap">
        <table class="db-table">
          <thead><tr><th>文件名</th><th>原始采集</th><th>页级融合</th><th>画像</th><th>图谱</th><th>关联</th><th>页数</th><th>创建时间</th><th></th></tr></thead>
          <tbody>
            <tr v-for="d in s.document_progresses" :key="d.id" :class="rowClass(d)">
              <td class="cell-name">{{ d.filename }}</td>
              <td><span class="tag" :class="statusClass(displayStatus(d, d.raw_status))">{{ statusText(displayStatus(d, d.raw_status)) }}</span></td>
              <td><span class="tag" :class="statusClass(displayStatus(d, d.fusion_status))">{{ statusText(displayStatus(d, d.fusion_status)) }}</span></td>
              <td><span class="tag" :class="statusClass(displayStatus(d, d.profile_status))">{{ statusText(displayStatus(d, d.profile_status)) }}</span></td>
              <td><span class="tag" :class="statusClass(displayStatus(d, d.graph_status))">{{ statusText(displayStatus(d, d.graph_status)) }}</span></td>
              <td><span class="tag" :class="statusClass(displayStatus(d, d.relation_status))">{{ statusText(displayStatus(d, d.relation_status)) }}</span></td>
              <td>{{ d.total_pages || '-' }}</td>
              <td class="cell-date">{{ fmtDate(d.created_at) }}</td>
              <td v-if="isFailed(d)">
                <button class="retrigger-btn" :disabled="isTriggered(d.id)" @click="handleRetrigger(d.id)">{{ triggeredSet.has(d.id) ? '已触发' : '🔄 重新触发' }}</button>
              </td>
              <td v-else-if="d.source_available === false" class="source-actions">
                <button class="retrigger-btn" @click="showReuploadHint(d)">重新上传</button>
                <button class="retrigger-btn danger" @click="archiveUnavailable(d)">删除无效记录</button>
              </td>
              <td v-else></td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div class="db-cols">
      <section class="db-section">
        <h3>卡住的文件 <span v-if="s.stuck_documents.length" class="badge">{{ s.stuck_documents.length }}</span></h3>
          <div v-if="s.stuck_documents.length" class="stuck-list">
            <div v-for="d in s.stuck_documents" :key="d.id" class="stuck-item">
              <span class="stuck-name">{{ d.filename }}</span>
              <span class="tag" :class="d.source_available === false ? 'source' : 'err'">{{ d.source_available === false ? '源文件不可用' : '失败' }}</span>
              <button v-if="d.source_available !== false" class="retrigger-btn" :disabled="isTriggered(d.id)" @click="handleRetrigger(d.id)">{{ triggeredSet.has(d.id) ? '已触发' : '🔄 重新触发' }}</button>
              <template v-else>
                <button class="retrigger-btn" @click="showReuploadHint(d)">重新上传</button>
                <button class="retrigger-btn danger" @click="archiveUnavailable(d)">删除无效记录</button>
              </template>
            </div>
          </div>
        <div v-else class="db-empty">暂无卡住文件</div>
      </section>

      <section class="db-section">
        <h3>实体类别分布</h3>
        <div v-if="hasCategories" class="cat-list">
          <div v-for="(cnt, cat) in s.entity_category_distribution" :key="cat" class="cat-row">
            <span class="cat-label">{{ cat }}</span>
            <span class="cat-bar"><span :style="{ width: barPct(cnt) + '%' }"></span></span>
            <span class="cat-num">{{ cnt }}</span>
          </div>
        </div>
        <div v-else class="db-empty">暂无实体</div>
      </section>
    </div>

    <section v-if="showGovernance" class="db-section">
      <h3>治理待办</h3>
      <div v-if="governanceCandidates.length" class="stuck-list">
        <div v-for="item in governanceCandidates" :key="item.id" class="stuck-item">
          <span class="stuck-name">{{ item.entity_name }} · {{ item.category }}</span>
          <span class="candidate-doc">资料 #{{ item.document_id }}</span>
        </div>
      </div>
      <div v-else-if="governanceCandidatesUnavailable" class="db-empty">仅管理员可查看治理候选明细</div>
      <div v-else class="db-empty">暂无治理待办</div>
    </section>

    <section v-if="s.duplicate_entity_groups.length" class="db-section">
      <h3>重复实体（待消歧）</h3>
      <div class="dup-list">
        <div v-for="g in s.duplicate_entity_groups" :key="g.name" class="dup-item">
          <span class="dup-name">{{ g.name }}</span>
          <span class="dup-cnt">{{ g.count }} 次</span>
        </div>
      </div>
    </section>

    <section v-if="s.recent_completions.length" class="db-section">
      <h3>最近完成分析</h3>
      <div class="recent-list">
        <div v-for="r in s.recent_completions" :key="r.id" class="recent-item">
          <span class="recent-name">{{ r.filename }}</span>
          <span class="recent-date">{{ fmtDate(r.completed_at) }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  apiDelete, getDashboardStats, getGovernanceCandidates, getPendingCount, startPipeline,
  type DashboardStats, type DocProgressEntry, type GovernanceCandidate,
} from '../api'

const props = defineProps<{
  initialShowGovernance?: boolean
}>()

const s = ref<DashboardStats>({
  total_documents: 0, completed_documents: 0, partial_documents: 0, running_documents: 0, failed_documents: 0,
  queued_documents: 0, paused_documents: 0, waiting_documents: 0, source_unavailable_documents: 0,
  total_entities: 0, total_graph_relations: 0, total_file_relations: 0,
  duplicate_entity_count: 0, duplicate_entity_groups: [],
  entity_category_distribution: {}, document_progresses: [], stuck_documents: [],
  recent_completions: [],
})
const loading = ref(true)
const loadError = ref('')
const triggeredSet = ref(new Set<number>())
const triggeringSet = ref(new Set<number>())
const pendingCount = ref(0)
const governanceCandidates = ref<GovernanceCandidate[]>([])
const governanceCandidatesUnavailable = ref(false)
const showGovernance = ref(props.initialShowGovernance === true)

const hasCategories = computed(() => Object.keys(s.value.entity_category_distribution).length > 0)

function statusClass(st: string): string {
  if (st === 'done') return 'ok'
  if (st === 'running' || st === 'collecting' || st === 'parsing' || st === 'fusing') return 'busy'
  if (st === 'queued') return 'queue'
  if (st === 'waiting' || st === 'pending') return 'wait'
  if (st === 'failed' || st === 'error') return 'err'
  if (st === 'source_unavailable') return 'source'
  if (st === 'paused') return 'pause'
  if (st === 'degraded') return 'warn'
  return ''
}
function statusText(st: string): string {
  if (st === 'done') return '✓ 完成'
  if (st === 'running' || st === 'collecting' || st === 'parsing' || st === 'fusing') return '进行中'
  if (st === 'queued') return '已入队'
  if (st === 'waiting' || st === 'pending') return '等待中'
  if (st === 'failed' || st === 'error') return '✗ 失败'
  if (st === 'source_unavailable') return '源文件不可用'
  if (st === 'degraded') return '部分完成'
  if (st === 'paused') return '暂停中'
  if (st === 'skipped') return '已忽略'
  return '等待中'
}
function displayStatus(d: DocProgressEntry, fallback: string): string {
  return d.source_available === false ? 'source_unavailable' : fallback
}
function rowClass(d: DocProgressEntry): string {
  if (d.source_available === false) return 'row-source'
  const statuses = stageStatuses(d)
  if (statuses.some(st => st === 'failed' || st === 'error')) return 'row-err'
  if (statuses.some(st => st === 'paused')) return 'row-paused'
  if (statuses.some(st => st === 'queued' || st === 'waiting' || st === 'pending' || st === 'running')) return 'row-busy'
  if (statuses.some(st => st === 'degraded')) return 'row-warn'
  if (statuses.every(st => st === 'done' || st === 'skipped')) return 'row-ok'
  return ''
}
function isFailed(d: DocProgressEntry): boolean {
  return d.source_available !== false && stageStatuses(d).some(st => st === 'failed' || st === 'error')
}
function stageStatuses(d: DocProgressEntry): string[] {
  return [d.raw_status, d.fusion_status, d.profile_status, d.graph_status, d.relation_status]
}
function barPct(cnt: number): number {
  const values = Object.values(s.value.entity_category_distribution) as number[]
  const max = Math.max(...values, 1)
  return Math.round(cnt / max * 100)
}
function fmtDate(iso: string): string {
  if (!iso) return '-'
  try { return new Date(iso).toLocaleDateString('zh-CN') } catch { return iso.slice(0, 10) }
}
function errorMessage(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback
}

async function refreshStats() {
  const errors: string[] = []
  try { s.value = await getDashboardStats() } catch (e: unknown) { errors.push(errorMessage(e, '看板统计加载失败')) }
  try {
    const pending = await getPendingCount()
    pendingCount.value = pending.pending_count
  } catch (e: unknown) { errors.push(errorMessage(e, '治理待办数量加载失败')) }
  try {
    governanceCandidatesUnavailable.value = false
    const candidates = await getGovernanceCandidates(5)
    governanceCandidates.value = candidates.items
  } catch (e: unknown) {
    governanceCandidates.value = []
    governanceCandidatesUnavailable.value = true
    errors.push(errorMessage(e, '治理候选加载失败'))
  }
  loadError.value = errors.join('；')
}

async function handleRetrigger(docId: number) {
  if (triggeredSet.value.has(docId) || triggeringSet.value.has(docId)) return
  triggeringSet.value = new Set(triggeringSet.value).add(docId)
  try {
    await startPipeline(docId)
    triggeredSet.value = new Set(triggeredSet.value).add(docId)
    setTimeout(() => {
      triggeredSet.value = new Set(triggeredSet.value)
      triggeredSet.value.delete(docId)
      triggeredSet.value = new Set(triggeredSet.value)
    }, 5000)
    await refreshStats()
  } catch (e) {
    console.error('[kb-dashboard] retrigger failed:', e)
    window.alert('重新触发失败: ' + String((e as Error).message || e))
  } finally {
    triggeringSet.value = new Set(triggeringSet.value)
    triggeringSet.value.delete(docId)
    triggeringSet.value = new Set(triggeringSet.value)
  }
}

function showReuploadHint(doc: DocProgressEntry) {
  window.alert(`请在桌面重新上传「${doc.filename}」，系统会自动登记新的知识库资料。若原文件在回收站，请先到桌面文件管理器恢复。`)
}

async function archiveUnavailable(doc: DocProgressEntry) {
  if (!window.confirm(`确认删除「${doc.filename}」这条无效知识库记录？这不会删除任何源文件。`)) return
  try {
    await apiDelete(`/knowledge/documents/${doc.id}`)
    await refreshStats()
  } catch (e) {
    console.error('[kb-dashboard] archive unavailable failed:', e)
    window.alert('删除无效记录失败: ' + String((e as Error).message || e))
  }
}

function isTriggered(docId: number): boolean {
  return triggeredSet.value.has(docId) || triggeringSet.value.has(docId)
}

onMounted(async () => {
  await refreshStats()
  loading.value = false
})
</script>

<style scoped>
.dashboard { padding: 4px 0; }
.db-title { margin: 0 0 16px; font-size: 20px; font-weight: 700; color: #1c3a4a; }
.db-error {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #f1b6ae;
  border-radius: 8px;
  background: #fff7f6;
  color: #b42318;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
}
.db-error button {
  flex: none;
  height: 28px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  cursor: pointer;
}
.db-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 12px; margin-bottom: 20px; }
.db-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; text-align: center; }
.db-card.ok { border-color: #b8e6d0; background: #f0faf5; }
.db-card.busy { border-color: #f0d78c; background: #fef7e0; }
.db-card.queue { border-color: #b8d8ff; background: #f1f7ff; }
.db-card.pause { border-color: #d4c8ff; background: #f6f3ff; }
.db-card.wait { border-color: #d7dee8; background: #f7f9fc; }
.db-card.err { border-color: #f5c6c2; background: #fef0ee; }
.db-card.warn { border-color: #ffd0a6; background: #fff7ed; }
.db-card.source { border-color: #ffd0a6; background: #fff7ed; }
.action-card { cursor: pointer; font: inherit; }
.action-card:hover { border-color: #2395bc; background: #f0f9fd; }
.db-num { display: block; font-size: 28px; font-weight: 800; color: #1c3a4a; line-height: 1.2; }
.db-card.ok .db-num { color: #1f9d5b; }
.db-card.busy .db-num { color: #c5851a; }
.db-card.queue .db-num { color: #2563eb; }
.db-card.pause .db-num { color: #6d55c7; }
.db-card.wait .db-num { color: #64748b; }
.db-card.err .db-num { color: #d4544b; }
.db-card.warn .db-num { color: #b45309; }
.db-card.source .db-num { color: #b45309; }
.db-label { font-size: 12px; color: #7c8da0; margin-top: 4px; display: block; }
.db-section { margin-bottom: 20px; }
.db-section h3 { margin: 0 0 10px; font-size: 15px; font-weight: 700; color: #1c3a4a; display: flex; align-items: center; gap: 8px; }
.badge { background: #e5534b; color: #fff; font-size: 11px; padding: 1px 7px; border-radius: 10px; }
.db-table-wrap { overflow-x: auto; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; }
.db-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.db-table th { background: #f6f9fc; padding: 10px 12px; text-align: left; font-weight: 600; color: #46586b; border-bottom: 1px solid #e3e9f2; white-space: nowrap; }
.db-table td { padding: 8px 12px; border-bottom: 1px solid #f0f3f7; color: #2a3a48; }
.db-table tr:last-child td { border-bottom: none; }
.db-table tr:hover td { background: #f7fbfe; }
.db-table tr.row-ok td { color: #1f9d5b; }
.db-table tr.row-busy td { color: #46586b; background: #f7f9fc; }
.db-table tr.row-paused td { color: #5b4bb2; background: #f6f3ff; }
.db-table tr.row-warn td { color: #9a5b12; background: #fff7ed; }
.db-table tr.row-err td { color: #d4544b; background: #fef0ee; }
.db-table tr.row-source td { color: #9a5b12; background: #fff7ed; }
.cell-name { max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cell-date { white-space: nowrap; font-size: 12px; color: #8aa0b5; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.tag.ok { background: #e3f6ec; color: #1f9d5b; }
.tag.busy { background: #fdf2dd; color: #c5851a; }
.tag.queue { background: #e7f0ff; color: #2563eb; }
.tag.pause { background: #eee9ff; color: #5b4bb2; }
.tag.wait { background: #eef2f7; color: #64748b; }
.tag.err { background: #fbe9e7; color: #d4544b; }
.tag.source { background: #fff0d9; color: #b45309; }
.tag.warn { background: #fff0d9; color: #b45309; }
.db-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.stuck-list, .dup-list, .recent-list { border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; overflow: hidden; }
.stuck-item, .dup-item, .recent-item { display: flex; align-items: center; justify-content: space-between; padding: 8px 14px; border-bottom: 1px solid #f0f3f7; font-size: 13px; }
.stuck-item:last-child, .dup-item:last-child, .recent-item:last-child { border-bottom: none; }
.stuck-name, .dup-name, .recent-name { color: #2a3a48; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.stuck-item .tag { flex: none; }
.source-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.dup-cnt { font-size: 12px; color: #8aa0b5; flex: none; }
.candidate-doc { font-size: 12px; color: #8aa0b5; flex: none; }
.recent-date { font-size: 12px; color: #8aa0b5; flex: none; }
.retrigger-btn { height: 28px; padding: 0 10px; border: 1px solid #2395bc; border-radius: 6px; background: #fff; color: #2395bc; font-size: 11px; font-weight: 600; cursor: pointer; white-space: nowrap; flex: none; transition: all .2s; }
.retrigger-btn:hover { background: #eaf6fb; }
.retrigger-btn:disabled { border-color: #c2cdda; color: #aab8c6; background: #f5f7fa; cursor: not-allowed; }
.retrigger-btn.danger { border-color: #f5c6c2; color: #b42318; }
.retrigger-btn.danger:hover { background: #fff1f0; }
.db-empty { color: #9aabbd; font-size: 13px; padding: 20px; text-align: center; border: 1px dashed #e3e9f2; border-radius: 10px; }
.cat-list { border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; padding: 8px 14px; }
.cat-row { display: flex; align-items: center; gap: 10px; padding: 5px 0; }
.cat-label { width: 70px; font-size: 12px; color: #46586b; flex: none; text-align: right; }
.cat-bar { flex: 1; height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.cat-bar span { display: block; height: 100%; background: linear-gradient(90deg, #2395bc, #31a1c6); border-radius: 4px; transition: width .4s; }
.cat-num { width: 30px; font-size: 12px; font-weight: 600; color: #2395bc; text-align: right; }
</style>
