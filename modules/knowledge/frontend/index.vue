<template>
  <div class="kb-app">
    <!-- 左侧:资料库 -->
    <aside class="kb-side">
      <div class="side-head">
        <span class="side-title">资料库</span>
        <button class="ghost-btn" title="刷新" @click="loadDocuments">⟳</button>
      </div>

      <label class="upload-box">
        <input type="file" class="file-input" @change="handleUpload" />
        <span class="up-plus">＋</span>
        <span class="up-text">上传资料 · 自动深度分析</span>
        <span class="up-hint">PDF / Word / 图片 / 文本</span>
      </label>

      <input v-model="keyword" class="search-mini" placeholder="筛选资料…" @keyup.enter="loadDocuments" />

      <div class="doc-list">
        <button
          v-for="doc in documents"
          :key="doc.id"
          class="doc-card"
          :class="{ active: activeId === doc.id }"
          @click="openDocument(doc)"
        >
          <span class="doc-ico">{{ fileIcon(doc.extension) }}</span>
          <span class="doc-body">
            <span class="doc-name">{{ doc.filename }}</span>
            <span class="doc-sub">
              <span class="dot" :class="statusClass(doc)"></span>
              {{ docStatusText(doc) }}
            </span>
          </span>
          <span v-if="livePercent(doc.id) !== null" class="doc-pct">{{ livePercent(doc.id) }}%</span>
        </button>
        <div v-if="!documents.length" class="empty-tip">还没有资料,上传一份开始</div>
      </div>
    </aside>

    <!-- 右侧:主区 -->
    <main class="kb-main">
      <div v-if="!active" class="welcome">
        <div class="welcome-card">
          <h1>知识库</h1>
          <p>上传企业资料,系统会逐页做多轮交叉印证、提炼画像、构建知识网络。</p>
          <p class="welcome-sub">左侧选择或上传一份资料即可开始。</p>
        </div>
      </div>

      <template v-else>
        <header class="main-head">
          <div class="head-left">
            <span class="head-ico">{{ fileIcon(active.extension) }}</span>
            <div>
              <h2>{{ active.filename }}</h2>
              <span class="head-meta">{{ active.total_pages || '—' }} 页 · {{ headStatusText }}</span>
            </div>
          </div>
          <div class="head-actions">
            <button
              class="primary-btn"
              :disabled="analyzing"
              @click="startAnalyze"
            >{{ analyzing ? '分析中…' : (progress?.overall_status === 'done' ? '重新分析' : '开始分析') }}</button>
            <button class="ghost-btn danger" @click="removeDocument">删除</button>
          </div>
        </header>

        <!-- 分析进度面板:用户只看进度,不看后台逻辑 -->
        <section v-if="showProgress" class="progress-panel">
          <div class="pp-top">
            <div class="pp-ring" :style="ringStyle">
              <span class="pp-ring-num">{{ progress?.overall_percent ?? 0 }}<i>%</i></span>
            </div>
            <div class="pp-top-text">
              <div class="pp-stage">{{ progressHeadline }}</div>
              <div class="pp-hint">{{ analyzing ? '正在处理,可关闭页面,稍后回来会自动接着显示进度' : '分析完成,下方查看结果' }}</div>
            </div>
          </div>

          <ol class="pp-steps">
            <li v-for="s in progress?.stages || []" :key="s.key" class="pp-step" :class="s.status">
              <span class="pp-dot">
                <template v-if="s.status === 'done'">✓</template>
                <template v-else-if="s.status === 'running'">●</template>
                <template v-else>○</template>
              </span>
              <span class="pp-label">{{ s.label }}</span>
              <span class="pp-track">
                <span class="pp-fill" :style="{ width: s.percent + '%' }"></span>
              </span>
              <span class="pp-count">{{ stepCount(s) }}</span>
            </li>
          </ol>
        </section>

        <!-- 结果区 -->
        <nav v-if="hasResult" class="tabs">
          <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
          <button :class="{ active: tab === 'reader' }" @click="tab = 'reader'">阅读</button>
          <button :class="{ active: tab === 'relation' }" @click="tab = 'relation'">关联</button>
          <button :class="{ active: tab === 'search' }" @click="tab = 'search'">检索</button>
        </nav>

        <!-- 概览:文件画像 -->
        <section v-if="hasResult && tab === 'overview'" class="pane">
          <div v-if="profile" class="profile-grid">
            <div class="pf-card pf-main">
              <div class="pf-tag">{{ profile.doc_type || '资料' }}</div>
              <h3>{{ profile.subject || active.filename }}</h3>
              <p class="pf-summary">{{ profile.doc_summary }}</p>
            </div>
            <div v-if="profile.core_conclusions" class="pf-card">
              <div class="pf-h">核心结论</div>
              <p>{{ profile.core_conclusions }}</p>
            </div>
            <div v-if="profile.applicable_scenarios" class="pf-card">
              <div class="pf-h">适用场景</div>
              <p>{{ profile.applicable_scenarios }}</p>
            </div>
            <div v-if="profileEntities.length" class="pf-card">
              <div class="pf-h">关键信息</div>
              <div class="chips">
                <span v-for="(e, i) in profileEntities" :key="i" class="chip">{{ e.name }}</span>
              </div>
            </div>
            <div v-if="profileChapters.length" class="pf-card pf-wide">
              <div class="pf-h">内容结构</div>
              <ul class="chapter-list">
                <li v-for="(c, i) in profileChapters" :key="i" @click="gotoPage(c.page)">
                  <span class="ch-page">P{{ c.page || '·' }}</span>
                  <span class="ch-title">{{ c.title }}</span>
                </li>
              </ul>
            </div>
          </div>
          <div v-else class="empty-tip pad">画像生成中或暂无,完成分析后显示</div>
        </section>

        <!-- 阅读:逐页融合内容(对外用第4层) -->
        <section v-if="hasResult && tab === 'reader'" class="pane">
          <article v-for="p in fusions" :key="p.page" :ref="el => setPageRef(p.page, el)" class="page-card">
            <div class="page-head">
              <span class="page-no">第 {{ p.page }} 页</span>
              <span v-if="p.page_title" class="page-title">{{ p.page_title }}</span>
              <span class="conf" :class="confClass(p.confidence)" :title="'融合置信度'">
                置信 {{ Math.round((p.confidence || 0) * 100) }}%
              </span>
            </div>
            <p class="page-text">{{ p.fused_text }}</p>
            <div v-if="p.conflicts && p.conflicts.length" class="conflict-note">
              ⚠ 多轮识别有 {{ p.conflicts.length }} 处差异,已按多数采信
            </div>
          </article>
          <div v-if="!fusions.length" class="empty-tip pad">完成分析后显示逐页内容</div>
        </section>

        <!-- 关联:跨文件知识网络 -->
        <section v-if="hasResult && tab === 'relation'" class="pane">
          <div v-if="relations.length" class="rel-list">
            <div class="rel-hint">这份资料与库中其它资料的关联(系统自动织网):</div>
            <button v-for="r in relations" :key="r.target_document_id" class="rel-card" @click="jumpDoc(r.target_document_id)">
              <span class="rel-name">{{ r.target_filename || ('资料 #' + r.target_document_id) }}</span>
              <span class="rel-bar"><span :style="{ width: relPct(r) + '%' }"></span></span>
              <span class="rel-score">{{ relPct(r) }}% 相关</span>
            </button>
          </div>
          <div v-else class="empty-tip pad">暂无关联。库里有相关资料时会自动建立联系。</div>
        </section>

        <!-- 检索 -->
        <section v-if="hasResult && tab === 'search'" class="pane">
          <div class="search-bar">
            <input v-model="query" class="search-input" placeholder="搜索全库知识内容…" @keyup.enter="runSearch" />
            <button class="primary-btn" :disabled="searching" @click="runSearch">{{ searching ? '搜索中' : '搜索' }}</button>
          </div>
          <article v-for="item in searchResults" :key="item.chunk_id" class="result-card" @click="jumpDoc(item.document_id)">
            <div class="result-head">
              <span class="result-doc">{{ docName(item.document_id) }}</span>
              <span class="result-page">第 {{ item.page || '·' }} 页</span>
            </div>
            <p>{{ item.text }}</p>
          </article>
          <div v-if="searched && !searchResults.length" class="empty-tip pad">没找到相关内容</div>
        </section>
      </template>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, nextTick } from 'vue'
import { initRuntime, platform } from '../runtime'
import {
  apiDelete, apiPost, apiGet,
  startPipeline, getProgress, getProgressBatch, getFusions, getProfile, getRelations, parseJsonField,
  type KnowledgeDocument, type DocumentProgress, type ProgressStage,
  type FusionPage, type DocumentProfile, type FileRelation, type SearchResult,
} from './api'

const documents = ref<KnowledgeDocument[]>([])
const active = ref<KnowledgeDocument | null>(null)
const activeId = computed(() => active.value?.id ?? null)
const keyword = ref('')
const tab = ref<'overview' | 'reader' | 'relation' | 'search'>('overview')

const progress = ref<DocumentProgress | null>(null)
const liveProgressMap = ref<Record<number, DocumentProgress>>({})
const fusions = ref<FusionPage[]>([])
const profile = ref<DocumentProfile | null>(null)
const relations = ref<FileRelation[]>([])

const query = ref('')
const searching = ref(false)
const searched = ref(false)
const searchResults = ref<SearchResult[]>([])

let pollTimer: number | null = null

// ── 计算属性 ──────────────────────────────
const analyzing = computed(() => progress.value?.overall_status === 'running')
const hasResult = computed(() => progress.value?.overall_status === 'done' || (fusions.value.length > 0))
const showProgress = computed(() => !!progress.value && progress.value.overall_status !== 'done')

const headStatusText = computed(() => {
  const p = progress.value
  if (!p) return '尚未分析'
  if (p.overall_status === 'done') return '分析完成'
  if (p.overall_status === 'failed') return '分析出错'
  if (p.overall_status === 'running') return p.current_stage + '…'
  return '待分析'
})

const progressHeadline = computed(() => {
  const p = progress.value
  if (!p) return ''
  if (p.overall_status === 'done') return '全部完成'
  if (p.overall_status === 'failed') return '分析出错,可重新分析'
  return '正在「' + p.current_stage + '」'
})

const ringStyle = computed(() => {
  const pct = progress.value?.overall_percent ?? 0
  return { background: `conic-gradient(#2395bc ${pct * 3.6}deg, #e6eef5 0deg)` }
})

const profileEntities = computed(() =>
  parseJsonField<Array<{ name: string }>>(profile.value?.key_entities, []).slice(0, 12),
)
const profileChapters = computed(() =>
  parseJsonField<Array<{ title?: string; page?: number }>>(profile.value?.chapter_structure, []),
)

// ── 工具 ──────────────────────────────
function fileIcon(ext?: string): string {
  const e = (ext || '').toLowerCase()
  if (e === 'pdf') return '📕'
  if (['doc', 'docx'].includes(e)) return '📘'
  if (['xls', 'xlsx'].includes(e)) return '📗'
  if (['ppt', 'pptx'].includes(e)) return '📙'
  if (['png', 'jpg', 'jpeg', 'gif', 'webp'].includes(e)) return '🖼'
  return '📄'
}
function docName(id: number): string {
  return documents.value.find(d => d.id === id)?.filename || ('资料 #' + id)
}
function livePercent(id: number): number | null {
  const p = liveProgressMap.value[id]
  if (!p) return null
  if (p.overall_status === 'done') return null
  return p.overall_percent
}
function statusClass(doc: KnowledgeDocument): string {
  const p = liveProgressMap.value[doc.id]
  if (p?.overall_status === 'running') return 'busy'
  if (p?.overall_status === 'done' || doc.fusion_status === 'done') return 'ok'
  if (doc.fusion_status === 'failed' || doc.raw_status === 'failed') return 'err'
  return 'idle'
}
function docStatusText(doc: KnowledgeDocument): string {
  const p = liveProgressMap.value[doc.id]
  if (p?.overall_status === 'running') return p.current_stage + '…'
  if (p?.overall_status === 'done' || doc.fusion_status === 'done') return '已分析'
  return '待分析'
}
function stepCount(s: ProgressStage): string {
  if (s.key === 'graph') return s.count ? `${s.count} 个实体` : (s.status === 'done' ? '完成' : '—')
  if (s.key === 'relation') return s.count ? `${s.count} 条关联` : (s.status === 'done' ? '完成' : '—')
  if (s.total <= 1) return s.status === 'done' ? '完成' : (s.status === 'running' ? '进行中' : '—')
  return `${s.done}/${s.total}`
}
function confClass(c?: number): string {
  const v = c || 0
  if (v >= 0.9) return 'high'
  if (v >= 0.75) return 'mid'
  return 'low'
}
function relPct(r: FileRelation): number {
  return Math.round((r.similarity_score || 0) * 100)
}

// ── 数据加载 ──────────────────────────────
async function loadDocuments(): Promise<void> {
  const params = new URLSearchParams({ page: '1', page_size: '80' })
  if (keyword.value) params.set('keyword', keyword.value)
  const page = await apiGet<{ items: KnowledgeDocument[] }>(`/knowledge/documents?${params.toString()}`)
  documents.value = page.items
  await handshakeAll()
}

// 握手:批量拉取所有"进行中/已完成"文档的真实进度,关页重开也能恢复
async function handshakeAll(): Promise<void> {
  const ids = documents.value.map(d => d.id)
  if (!ids.length) return
  try {
    const map = await getProgressBatch(ids)
    const normalized: Record<number, DocumentProgress> = {}
    for (const k of Object.keys(map)) normalized[Number(k)] = map[k]
    liveProgressMap.value = normalized
    // 有任何在跑的就开启轮询
    if (Object.values(normalized).some(p => p.overall_status === 'running')) ensurePolling()
  } catch { /* 忽略握手失败 */ }
}

async function openDocument(doc: KnowledgeDocument): Promise<void> {
  active.value = doc
  tab.value = 'overview'
  progress.value = liveProgressMap.value[doc.id] || await getProgress(doc.id)
  fusions.value = []
  profile.value = null
  relations.value = []
  searchResults.value = []
  searched.value = false
  if (progress.value.overall_status === 'running') ensurePolling()
  if (hasResult.value) await loadResult(doc.id)
}

async function loadResult(docId: number): Promise<void> {
  const [f, pf, rel] = await Promise.all([
    getFusions(docId).then(r => r.items).catch(() => []),
    getProfile(docId).catch(() => null),
    getRelations(docId).catch(() => []),
  ])
  if (active.value?.id !== docId) return
  fusions.value = f
  profile.value = pf
  relations.value = rel
}

async function handleUpload(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const uploaded = await platform.files.upload(file)
    const doc = await apiPost<KnowledgeDocument>('/knowledge/documents', { file_id: uploaded.id })
    await loadDocuments()
    const fresh = documents.value.find(d => d.id === doc.id) || doc
    await openDocument(fresh)
    await startAnalyze()
  } catch (error) {
    window.alert((error as Error).message)
  } finally {
    input.value = ''
  }
}

async function startAnalyze(): Promise<void> {
  if (!active.value) return
  try {
    await startPipeline(active.value.id)
    progress.value = await getProgress(active.value.id)
    ensurePolling()
  } catch (error) {
    window.alert((error as Error).message)
  }
}

async function removeDocument(): Promise<void> {
  if (!active.value) return
  if (!window.confirm('确认删除该资料及其分析结果?')) return
  await apiDelete(`/knowledge/documents/${active.value.id}`)
  active.value = null
  progress.value = null
  await loadDocuments()
}

// ── 轮询(实时同步后端细颗粒进度) ──────────────────────────────
function ensurePolling(): void {
  if (pollTimer !== null) return
  pollTimer = window.setInterval(pollTick, 1500)
}
function stopPolling(): void {
  if (pollTimer !== null) { window.clearInterval(pollTimer); pollTimer = null }
}
async function pollTick(): Promise<void> {
  const ids = documents.value
    .filter(d => liveProgressMap.value[d.id]?.overall_status === 'running' || d.id === active.value?.id)
    .map(d => d.id)
  if (!ids.length) { stopPolling(); return }
  try {
    const map = await getProgressBatch(ids)
    for (const k of Object.keys(map)) liveProgressMap.value[Number(k)] = map[k]
    // 当前打开的文档:更新进度面板,完成时加载结果
    if (active.value) {
      const cur = map[String(active.value.id)]
      if (cur) {
        const wasRunning = progress.value?.overall_status === 'running'
        progress.value = cur
        if (wasRunning && cur.overall_status === 'done') await loadResult(active.value.id)
      }
    }
    if (!Object.values(map).some(p => p.overall_status === 'running')) stopPolling()
  } catch { /* 网络抖动忽略,下次再试 */ }
}

// ── 检索 ──────────────────────────────
async function runSearch(): Promise<void> {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const data = await apiPost<{ results: SearchResult[] }>('/knowledge/search', { query: query.value, top_k: 10 })
    searchResults.value = data.results
    searched.value = true
  } finally {
    searching.value = false
  }
}

// ── 页面跳转 ──────────────────────────────
const pageRefs = ref<Record<number, HTMLElement>>({})
function setPageRef(page: number, el: unknown): void {
  if (el) pageRefs.value[page] = el as HTMLElement
}
async function gotoPage(page?: number): Promise<void> {
  if (!page) return
  tab.value = 'reader'
  await nextTick()
  pageRefs.value[page]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
async function jumpDoc(docId: number): Promise<void> {
  const doc = documents.value.find(d => d.id === docId)
  if (doc) await openDocument(doc)
}

onMounted(async () => {
  await initRuntime('knowledge')
  await loadDocuments()
})
onUnmounted(stopPolling)
</script>

<style scoped>
.kb-app {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  height: 100%;
  min-height: 640px;
  background: #f3f6fb;
  color: #1f2a37;
  font-family: 苹方, "微软雅黑", 宋体, sans-serif;
}

/* 左侧 */
.kb-side {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: #fff;
  border-right: 1px solid #e3e9f2;
  min-width: 0;
}
.side-head { display: flex; align-items: center; justify-content: space-between; }
.side-title { font-size: 16px; font-weight: 700; }
.upload-box {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 4px; padding: 18px 12px; cursor: pointer;
  border: 1.5px dashed #9cc2d6; border-radius: 12px;
  background: linear-gradient(180deg, #f4fbff, #eef7fc); color: #2395bc;
  transition: border-color .15s, background .15s;
}
.upload-box:hover { border-color: #2395bc; background: #e7f4fb; }
.file-input { display: none; }
.up-plus { font-size: 24px; font-weight: 300; line-height: 1; }
.up-text { font-size: 13px; font-weight: 600; }
.up-hint { font-size: 11px; color: #8aa0b5; }
.search-mini {
  height: 34px; padding: 0 12px; border: 1px solid #d5dfeb; border-radius: 8px;
  background: #fff; color: #1f2a37; outline: none;
}
.search-mini:focus { border-color: #2395bc; }
.doc-list { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 6px; }
.doc-card {
  display: flex; align-items: center; gap: 10px; width: 100%; padding: 10px;
  text-align: left; cursor: pointer; border: 1px solid #eaeef4; border-radius: 10px;
  background: #fff; transition: all .12s;
}
.doc-card:hover { border-color: #bcd6e6; background: #f7fbfe; }
.doc-card.active { border-color: #2395bc; background: #eaf6fb; box-shadow: 0 0 0 1px #2395bc inset; }
.doc-ico { font-size: 20px; }
.doc-body { display: flex; flex-direction: column; gap: 3px; min-width: 0; flex: 1; }
.doc-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-sub { font-size: 11px; color: #7c8da0; display: flex; align-items: center; gap: 5px; }
.dot { width: 7px; height: 7px; border-radius: 50%; flex: none; }
.dot.ok { background: #2bb673; }
.dot.busy { background: #f0b240; animation: pulse 1s infinite; }
.dot.err { background: #e5534b; }
.dot.idle { background: #c2cdda; }
.doc-pct { font-size: 11px; font-weight: 700; color: #f0941f; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* 主区 */
.kb-main { display: flex; flex-direction: column; min-width: 0; padding: 18px 20px; gap: 14px; overflow: hidden; }
.welcome { flex: 1; display: flex; align-items: center; justify-content: center; }
.welcome-card { text-align: center; max-width: 420px; }
.welcome-card h1 { font-size: 26px; margin: 0 0 12px; color: #1c3a4a; }
.welcome-card p { margin: 4px 0; color: #5a6b7d; line-height: 1.7; }
.welcome-sub { font-size: 13px; color: #8aa0b5; }

.main-head { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding-bottom: 12px; border-bottom: 1px solid #e3e9f2; }
.head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.head-ico { font-size: 30px; }
.main-head h2 { margin: 0; font-size: 18px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-meta { font-size: 12px; color: #7c8da0; }
.head-actions { display: flex; gap: 8px; flex: none; }
.primary-btn {
  height: 36px; padding: 0 18px; border: none; border-radius: 8px; cursor: pointer;
  background: #2395bc; color: #fff; font-weight: 600; font-size: 13px;
}
.primary-btn:hover { background: #1f86a9; }
.primary-btn:disabled { background: #aebfcc; cursor: not-allowed; }
.ghost-btn { height: 36px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; cursor: pointer; }
.ghost-btn:hover { border-color: #bcd6e6; }
.ghost-btn.danger:hover { border-color: #e5534b; color: #e5534b; }

/* 进度面板 */
.progress-panel { border: 1px solid #e3e9f2; border-radius: 14px; background: #fff; padding: 20px; box-shadow: 0 2px 10px rgba(35,149,188,.05); }
.pp-top { display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.pp-ring { width: 76px; height: 76px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; }
.pp-ring::before { content: ''; position: absolute; width: 56px; height: 56px; border-radius: 50%; background: #fff; }
.pp-ring { position: relative; }
.pp-ring-num { position: relative; font-size: 20px; font-weight: 800; color: #1c3a4a; }
.pp-ring-num i { font-size: 12px; font-style: normal; color: #7c8da0; }
.pp-stage { font-size: 16px; font-weight: 700; color: #1c3a4a; }
.pp-hint { font-size: 12px; color: #8aa0b5; margin-top: 4px; }
.pp-steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 12px; }
.pp-step { display: grid; grid-template-columns: 22px 80px 1fr 70px; align-items: center; gap: 10px; }
.pp-dot { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; background: #eef2f7; color: #aab8c6; }
.pp-step.done .pp-dot { background: #2bb673; color: #fff; }
.pp-step.running .pp-dot { background: #2395bc; color: #fff; animation: pulse 1s infinite; }
.pp-label { font-size: 13px; color: #46586b; }
.pp-step.pending .pp-label { color: #aab8c6; }
.pp-track { height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.pp-fill { display: block; height: 100%; background: linear-gradient(90deg, #2395bc, #31a1c6); border-radius: 4px; transition: width .4s ease; }
.pp-step.done .pp-fill { background: #2bb673; }
.pp-count { font-size: 12px; font-weight: 600; color: #5a6b7d; text-align: right; }

/* 标签页 */
.tabs { display: flex; gap: 4px; border-bottom: 1px solid #e3e9f2; flex: none; }
.tabs button { height: 38px; padding: 0 18px; border: none; background: transparent; color: #5a6b7d; cursor: pointer; font-size: 14px; border-radius: 8px 8px 0 0; }
.tabs button:hover { color: #2395bc; }
.tabs button.active { color: #2395bc; font-weight: 700; box-shadow: inset 0 -2px 0 #2395bc; }

.pane { flex: 1; min-height: 0; overflow: auto; }

/* 画像 */
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.pf-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; }
.pf-main { grid-column: 1 / -1; background: linear-gradient(135deg, #f0f9fd, #eaf6fb); border-color: #cfe7f1; }
.pf-wide { grid-column: 1 / -1; }
.pf-tag { display: inline-block; padding: 2px 10px; border-radius: 20px; background: #2395bc; color: #fff; font-size: 12px; margin-bottom: 8px; }
.pf-main h3 { margin: 0 0 8px; font-size: 18px; color: #1c3a4a; }
.pf-summary { margin: 0; line-height: 1.75; color: #46586b; }
.pf-h { font-size: 13px; font-weight: 700; color: #2395bc; margin-bottom: 8px; }
.pf-card p { margin: 0; line-height: 1.7; color: #46586b; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 4px 10px; border-radius: 16px; background: #eef5f9; color: #2c6177; font-size: 12px; }
.chapter-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 4px; }
.chapter-list li { display: flex; gap: 10px; padding: 7px 8px; border-radius: 8px; cursor: pointer; }
.chapter-list li:hover { background: #f0f9fd; }
.ch-page { color: #2395bc; font-weight: 700; font-size: 12px; flex: none; width: 36px; }
.ch-title { color: #46586b; font-size: 13px; }

/* 阅读 */
.page-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; margin-bottom: 12px; }
.page-head { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.page-no { font-weight: 700; color: #1c3a4a; }
.page-title { color: #5a6b7d; font-size: 13px; flex: 1; }
.conf { font-size: 12px; padding: 2px 8px; border-radius: 12px; font-weight: 600; }
.conf.high { background: #e3f6ec; color: #1f9d5b; }
.conf.mid { background: #fdf2dd; color: #c5851a; }
.conf.low { background: #fbe9e7; color: #d4544b; }
.page-text { margin: 0; line-height: 1.8; color: #2a3a48; white-space: pre-wrap; }
.conflict-note { margin-top: 10px; padding: 6px 10px; border-radius: 8px; background: #fdf6e8; color: #b07d18; font-size: 12px; }

/* 关联 */
.rel-hint { font-size: 13px; color: #5a6b7d; margin-bottom: 12px; }
.rel-list { display: flex; flex-direction: column; gap: 10px; }
.rel-card { display: grid; grid-template-columns: 1fr 160px 80px; align-items: center; gap: 12px; width: 100%; padding: 12px 14px; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; cursor: pointer; text-align: left; }
.rel-card:hover { border-color: #2395bc; background: #f7fbfe; }
.rel-name { font-weight: 600; color: #1c3a4a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rel-bar { height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.rel-bar span { display: block; height: 100%; background: linear-gradient(90deg, #2395bc, #31a1c6); }
.rel-score { font-size: 12px; font-weight: 700; color: #2395bc; text-align: right; }

/* 检索 */
.search-bar { display: flex; gap: 8px; margin-bottom: 14px; }
.search-input { flex: 1; height: 38px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; outline: none; }
.search-input:focus { border-color: #2395bc; }
.result-card { border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; padding: 14px; margin-bottom: 10px; cursor: pointer; }
.result-card:hover { border-color: #2395bc; }
.result-head { display: flex; justify-content: space-between; font-size: 12px; color: #7c8da0; margin-bottom: 8px; }
.result-doc { font-weight: 600; color: #2395bc; }
.result-card p { margin: 0; line-height: 1.7; color: #2a3a48; }

/* 通用 */
.empty-tip { color: #9aabbd; font-size: 13px; text-align: center; padding: 14px; }
.empty-tip.pad { padding: 40px; }
</style>
