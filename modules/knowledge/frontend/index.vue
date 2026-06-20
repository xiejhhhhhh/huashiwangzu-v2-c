<template>
  <div class="knowledge-app">
    <aside class="kb-sidebar">
      <div class="pane-title">资料</div>

      <label class="upload-box">
        <input type="file" class="file-input" @change="handleFileChange" />
        <span class="upload-icon">↑</span>
        <span class="upload-text">选择资料上传</span>
      </label>

      <div class="toolbar-row">
        <input v-model="keyword" class="text-input" placeholder="搜索资料" @keyup.enter="loadDocuments" />
        <button class="icon-button" @click="loadDocuments">刷新</button>
      </div>

      <div class="document-list">
        <button
          v-for="doc in documents"
          :key="doc.id"
          class="document-item"
          :class="{ active: activeDocument?.id === doc.id }"
          @click="openDocument(doc)"
        >
          <span class="doc-name">{{ doc.filename }}</span>
          <span class="doc-meta">{{ doc.extension }} · {{ doc.parse_status }} · {{ doc.total_chunks }}块</span>
        </button>
      </div>
    </aside>

    <main class="kb-main">
      <header class="kb-header">
        <div>
          <h2>{{ activeDocument?.filename || '知识库' }}</h2>
          <span>{{ statusText }}</span>
        </div>
        <div class="header-actions">
          <button class="primary-button" :disabled="!activeDocument || parsing" @click="parseActiveDocument">
            {{ parsing ? '解析中' : '解析入库' }}
          </button>
          <button class="plain-button" :disabled="!activeDocument" @click="deleteActiveDocument">删除</button>
        </div>
      </header>

      <section class="search-panel">
        <input v-model="query" class="text-input grow" placeholder="搜索知识库内容" @keyup.enter="searchKnowledge" />
        <input v-model.number="topK" class="number-input" type="number" min="1" max="20" />
        <button class="primary-button" :disabled="searching" @click="searchKnowledge">
          {{ searching ? '搜索中' : '搜索' }}
        </button>
      </section>

      <nav class="tabs">
        <button :class="{ active: activeTab === 'reader' }" @click="activeTab = 'reader'">阅读</button>
        <button :class="{ active: activeTab === 'search' }" @click="activeTab = 'search'">检索</button>
        <button :class="{ active: activeTab === 'entities' }" @click="activeTab = 'entities'">实体词典</button>
        <button :class="{ active: activeTab === 'governance' }" @click="activeTab = 'governance'">治理</button>
      </nav>

      <section v-if="activeTab === 'reader'" class="content-pane">
        <div v-if="chunks.length" class="chunk-list">
          <article v-for="chunk in chunks" :key="chunk.id" class="chunk-card">
            <div class="chunk-head">
              <span>{{ chunk.block_type }}</span>
              <span>第 {{ chunk.page || '-' }} 页 · #{{ chunk.chunk_index }}</span>
            </div>
            <p>{{ chunk.text }}</p>
          </article>
        </div>
        <div v-else class="empty-state">选择资料并解析后显示内容块</div>
      </section>

      <section v-if="activeTab === 'search'" class="content-pane">
        <div v-if="searchResults.length" class="chunk-list">
          <article v-for="item in searchResults" :key="item.chunk_id" class="chunk-card result-card" @click="openResult(item)">
            <div class="chunk-head">
              <span>相关度 {{ item.rrf_score }}</span>
              <span>文档 {{ item.document_id }} · 页 {{ item.page || '-' }}</span>
            </div>
            <p>{{ item.text }}</p>
          </article>
        </div>
        <div v-else class="empty-state">输入关键词检索资料内容</div>
      </section>

      <section v-if="activeTab === 'entities'" class="content-pane">
        <div class="entity-toolbar">
          <input v-model="entityKeyword" class="text-input grow" placeholder="搜索实体" @keyup.enter="loadEntities" />
          <button class="plain-button" @click="loadEntities">查询</button>
        </div>
        <table class="data-table">
          <thead>
            <tr><th>实体</th><th>类型</th><th>状态</th><th>说明</th></tr>
          </thead>
          <tbody>
            <tr v-for="entity in entities" :key="entity.id" @click="loadGraphContext(entity)">
              <td>{{ entity.name }}</td>
              <td>{{ entity.category }}</td>
              <td>{{ entity.status }}</td>
              <td>{{ entity.description }}</td>
            </tr>
          </tbody>
        </table>
        <GraphPanel :nodes="graphNodes" :edges="graphEdges" :center-node-id="centerGraphNodeId" />
      </section>

      <section v-if="activeTab === 'governance'" class="content-pane">
        <div class="entity-toolbar">
          <select v-model="auditStatus" class="select-input" @change="loadCandidates">
            <option value="pending">待确认</option>
            <option value="approved">已通过</option>
            <option value="rejected">已驳回</option>
          </select>
          <button class="plain-button" @click="loadCandidates">刷新</button>
        </div>
        <table class="data-table">
          <thead>
            <tr><th>候选实体</th><th>类型</th><th>置信度</th><th>证据</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="candidate in candidates" :key="candidate.id">
              <td>{{ candidate.entity_name }}</td>
              <td>{{ candidate.category }}</td>
              <td>{{ candidate.confidence }}</td>
              <td>{{ candidate.excerpt }}</td>
              <td class="action-cell">
                <button class="small-button" @click="approveCandidate(candidate.id)">通过</button>
                <button class="small-button" @click="rejectCandidate(candidate.id)">驳回</button>
              </td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { initRuntime, platform } from '../runtime'
import GraphPanel, { type GraphEdge, type GraphNode } from './GraphPanel.vue'
import {
  apiDelete,
  apiGet,
  apiPost,
  type ChunkItem,
  type EntityItem,
  type GovernanceCandidate,
  type KnowledgeDocument,
  type SearchResult,
} from './api'

const documents = ref<KnowledgeDocument[]>([])
const activeDocument = ref<KnowledgeDocument | null>(null)
const chunks = ref<ChunkItem[]>([])
const keyword = ref('')
const query = ref('')
const topK = ref(8)
const searching = ref(false)
const parsing = ref(false)
const activeTab = ref('reader')
const searchResults = ref<SearchResult[]>([])
const entities = ref<EntityItem[]>([])
const entityKeyword = ref('')
const graphNodes = ref<GraphNode[]>([])
const graphEdges = ref<GraphEdge[]>([])
const centerGraphNodeId = ref<number | null>(null)
const candidates = ref<GovernanceCandidate[]>([])
const auditStatus = ref('pending')

const statusText = computed(() => {
  if (!activeDocument.value) return '上传资料、解析入库，然后通过 Agent 技能检索。'
  const doc = activeDocument.value
  return `解析 ${doc.parse_status} · 向量 ${doc.vector_status} · ${doc.total_pages}页 · ${doc.total_chunks}块`
})

function notify(message: string): void {
  window.setTimeout(() => window.alert(message), 0)
}

async function loadDocuments(): Promise<void> {
  const params = new URLSearchParams({ page: '1', page_size: '50' })
  if (keyword.value) params.set('keyword', keyword.value)
  const page = await apiGet<{ items: KnowledgeDocument[] }>(`/knowledge/documents?${params.toString()}`)
  documents.value = page.items
}

async function handleFileChange(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const uploaded = await platform.files.upload(file)
    const doc = await apiPost<KnowledgeDocument>('/knowledge/documents', { file_id: uploaded.id })
    notify('资料已登记')
    await loadDocuments()
    await openDocument(doc)
  } catch (error) {
    notify((error as Error).message)
  } finally {
    input.value = ''
  }
}

async function openDocument(doc: KnowledgeDocument): Promise<void> {
  activeDocument.value = doc
  chunks.value = []
  if (doc.total_chunks > 0) {
    chunks.value = await apiGet<ChunkItem[]>(`/knowledge/documents/${doc.id}/chunks`)
  }
}

async function parseActiveDocument(): Promise<void> {
  if (!activeDocument.value) return
  parsing.value = true
  try {
    const result = await apiPost<{ document: KnowledgeDocument }>('/knowledge/documents/parse', {
      document_id: activeDocument.value.id,
      extract_graph: true,
    })
    activeDocument.value = result.document
    notify('解析和索引完成')
    await loadDocuments()
    await openDocument(result.document)
    await loadEntities()
    await loadCandidates()
  } catch (error) {
    notify((error as Error).message)
  } finally {
    parsing.value = false
  }
}

async function deleteActiveDocument(): Promise<void> {
  if (!activeDocument.value) return
  if (!window.confirm('确认删除该知识库资料？')) return
  await apiDelete(`/knowledge/documents/${activeDocument.value.id}`)
  activeDocument.value = null
  chunks.value = []
  await loadDocuments()
}

async function searchKnowledge(): Promise<void> {
  if (!query.value.trim()) return
  searching.value = true
  try {
    const data = await apiPost<{ results: SearchResult[] }>('/knowledge/search', {
      query: query.value,
      top_k: topK.value,
    })
    searchResults.value = data.results
    activeTab.value = 'search'
  } catch (error) {
    notify((error as Error).message)
  } finally {
    searching.value = false
  }
}

async function openResult(item: SearchResult): Promise<void> {
  const doc = documents.value.find((entry) => entry.id === item.document_id)
  if (doc) await openDocument(doc)
  activeTab.value = 'reader'
}

async function loadEntities(): Promise<void> {
  const params = new URLSearchParams()
  if (entityKeyword.value) params.set('keyword', entityKeyword.value)
  entities.value = await apiGet<EntityItem[]>(`/knowledge/entities?${params.toString()}`)
}

async function loadGraphContext(row: EntityItem): Promise<void> {
  const data = await apiGet<{ node: GraphNode | null; nodes: GraphNode[]; edges: GraphEdge[] }>(`/knowledge/entities/${row.id}/graph`)
  graphNodes.value = data.nodes
  graphEdges.value = data.edges
  centerGraphNodeId.value = data.node?.id ?? null
}

async function loadCandidates(): Promise<void> {
  const params = new URLSearchParams({ audit_status: auditStatus.value, page: '1', page_size: '50' })
  const page = await apiGet<{ items: GovernanceCandidate[] }>(`/knowledge/governance/candidates?${params.toString()}`)
  candidates.value = page.items
}

async function approveCandidate(id: number): Promise<void> {
  await apiPost(`/knowledge/governance/candidates/${id}/approve`)
  await loadCandidates()
}

async function rejectCandidate(id: number): Promise<void> {
  await apiPost(`/knowledge/governance/candidates/${id}/reject`)
  await loadCandidates()
}

onMounted(async () => {
  await initRuntime('knowledge')
  await Promise.all([loadDocuments(), loadEntities(), loadCandidates()])
})
</script>

<style scoped>
.knowledge-app {
  display: grid;
  grid-template-columns: 310px minmax(0, 1fr);
  height: 100%;
  min-height: 620px;
  background: #f6f8fb;
  color: #1f2937;
}

.kb-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-right: 1px solid #dfe5ef;
  background: #ffffff;
  min-width: 0;
}

.pane-title,
.kb-header h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
}

.upload-box {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 78px;
  border: 1px dashed #9db6d8;
  border-radius: 8px;
  background: #f7fbff;
  color: #3b5f8f;
  cursor: pointer;
}

.file-input {
  display: none;
}

.upload-icon {
  font-size: 18px;
  font-weight: 700;
}

.upload-text,
.doc-meta,
.kb-header span,
.chunk-head {
  font-size: 12px;
  color: #6b7280;
}

.toolbar-row,
.search-panel,
.entity-toolbar,
.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.text-input,
.number-input,
.select-input {
  min-height: 32px;
  padding: 0 10px;
  border: 1px solid #cfd8e6;
  border-radius: 6px;
  background: #fff;
  color: #1f2937;
}

.grow {
  flex: 1;
  min-width: 0;
}

.number-input {
  width: 72px;
}

button {
  min-height: 32px;
  border: 1px solid #cfd8e6;
  border-radius: 6px;
  background: #fff;
  color: #1f2937;
  cursor: pointer;
}

button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.primary-button {
  padding: 0 14px;
  border-color: #2563eb;
  background: #2563eb;
  color: #fff;
}

.plain-button,
.icon-button,
.small-button {
  padding: 0 12px;
}

.small-button {
  min-height: 26px;
  font-size: 12px;
}

.document-list,
.content-pane {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.document-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  margin-bottom: 8px;
  text-align: left;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
}

.document-item:hover,
.document-item.active {
  border-color: #2563eb;
  background: #eff6ff;
}

.doc-name {
  overflow: hidden;
  font-size: 14px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.kb-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 16px;
  gap: 12px;
}

.kb-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #dfe5ef;
}

.search-panel {
  padding: 10px;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  background: #ffffff;
}

.tabs {
  display: flex;
  gap: 6px;
  border-bottom: 1px solid #dfe5ef;
}

.tabs button {
  border: 0;
  border-radius: 6px 6px 0 0;
  background: transparent;
  padding: 0 14px;
}

.tabs button.active {
  background: #ffffff;
  color: #2563eb;
  box-shadow: inset 0 -2px 0 #2563eb;
}

.chunk-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chunk-card {
  padding: 12px 14px;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  background: #ffffff;
}

.result-card {
  cursor: pointer;
}

.result-card:hover {
  border-color: #2563eb;
}

.chunk-head {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
}

.chunk-card p {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.65;
}

.empty-state {
  padding: 18px;
  border: 1px solid #dfe5ef;
  border-radius: 8px;
  background: #ffffff;
  color: #6b7280;
}

.data-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 10px;
  background: #fff;
}

.data-table th,
.data-table td {
  padding: 9px 10px;
  border-bottom: 1px solid #e5e7eb;
  text-align: left;
  vertical-align: top;
  font-size: 13px;
}

.data-table tbody tr:hover {
  background: #f8fafc;
}

.action-cell {
  display: flex;
  gap: 6px;
}
</style>
