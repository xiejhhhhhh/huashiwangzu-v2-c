<template>
  <div
    class="kb-app"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="finder"
  >
    <MacAppShell layout="finder" :sidebar-width="220">
      <template #sidebar>
    <!-- 左侧：工作台入口 + 文件树 -->
    <aside class="kb-side">
      <button class="ws-btn" :class="{ active: showWorkspace }" @click="openWorkspace">
        <LayoutDashboard :size="15" />
        工作台
      </button>
      <button v-if="isAdminOrEditor" class="ws-btn" @click="openDashboard" :class="{ active: showDashboard }">
        <ChartNoAxesCombined :size="15" />
        看板
      </button>

      <input v-model="keyword" class="search-mini" placeholder="筛选文件…" />

      <div v-if="runningCount > 0" class="running-hint" @click="jumpToFirstRunning">
        ⚙ {{ runningCount }} 个文件分析中…
      </div>

      <div class="tree-wrap">
        <div v-if="treeLoading" class="empty-tip">加载中…</div>
        <div v-else-if="treeError" class="tree-error" role="alert">
          <span>{{ treeError }}</span>
          <button type="button" @click="loadFileTree">重试</button>
        </div>
        <div v-else-if="!fileTree.length" class="empty-tip">暂无可分析文件</div>
        <button
          v-for="node in visibleTree"
          :key="node._render_key || node.node_key"
          class="tree-node"
          :style="{ paddingLeft: (node._depth || 0) * 16 + 10 + 'px' }"
          :class="{ active: activeId && node.kb_doc_id === activeId }"
          @click="node.is_folder ? toggleFolder(node) : openDocByNode(node)"
        >
          <span class="tree-arrow" v-if="node.is_folder">{{ node._open ? '▼' : '▶' }}</span>
          <span class="tree-icon">{{ node.is_folder ? (node._open ? '📂' : '📁') : fileIcon(node._ext) }}</span>
          <span class="tree-name">{{ node.name }}</span>
          <span v-if="!node.is_folder && node.kb_status" class="tree-dot" :class="statusDotClass(node.kb_status)"></span>
          <span v-if="!node.is_folder && node._pct !== null" class="tree-pct">{{ node._pct }}%</span>
        </button>
      </div>
    </aside>
      </template>

      <template #toolbar>
        <div class="kb-toolbar">
          <div class="kb-toolbar-copy">
            <strong>知识库</strong>
            <span>资料检索 · 画像 · 工作台</span>
          </div>
        </div>
      </template>

    <!-- 右侧主区 -->
    <main class="kb-main">
      <section v-if="showWorkspace && !active" class="workspace-overview">
        <header class="workspace-head workspace-head-glass">
          <div>
            <h1>知识库工作台</h1>
            <p>查看资料处理状态并继续最近的工作。</p>
          </div>
          <button v-if="runningCount" class="ghost-btn" @click="jumpToFirstRunning">
            <LoaderCircle :size="15" class="spin" />
            查看分析任务
          </button>
        </header>

        <div class="workspace-stats">
          <article class="stat-item">
            <Files :size="18" />
            <strong>{{ documents.length }}</strong>
            <span>已收录</span>
          </article>
          <article class="stat-item is-success">
            <CircleCheck :size="18" />
            <strong>{{ analyzedDocCount }}</strong>
            <span>已完成</span>
          </article>
          <article class="stat-item is-running">
            <LoaderCircle :size="18" :class="{ spin: runningCount > 0 }" />
            <strong>{{ runningCount }}</strong>
            <span>处理中</span>
          </article>
          <article class="stat-item is-warning">
            <TriangleAlert :size="18" />
            <strong>{{ failedDocumentCount }}</strong>
            <span>需要处理</span>
          </article>
        </div>

        <section class="recent-section">
          <div class="section-title">
            <div>
              <h2>最近资料</h2>
              <span v-if="pendingDocumentCount">{{ pendingDocumentCount }} 个资料等待分析</span>
            </div>
          </div>
          <div v-if="recentDocuments.length" class="recent-list">
            <button v-for="doc in recentDocuments" :key="doc.id" class="recent-row" @click="openDocument(doc)">
              <span class="recent-icon">{{ fileIcon(doc.extension) }}</span>
              <span class="recent-copy">
                <strong>{{ doc.filename }}</strong>
                <small>{{ doc.total_pages || 0 }} 页 · {{ doc.total_chunks || 0 }} 个内容块</small>
              </span>
              <span class="document-state" :class="documentStatus(doc)">{{ documentStatusText(doc) }}</span>
              <ChevronRight :size="15" />
            </button>
          </div>
          <div v-else class="workspace-empty">
            <FolderSearch :size="34" />
            <strong>还没有可用资料</strong>
            <span>从桌面拖入文件后会显示在这里。</span>
          </div>
        </section>
      </section>

      <!-- 看板 -->
      <template v-else-if="showDashboard && !active">
        <DashboardView :initial-show-governance="showGovernanceFromPayload" />
      </template>

      <!-- 无选中：欢迎 -->
      <div v-else-if="!active" class="welcome">
        <div class="welcome-card">
          <h1>知识库</h1>
          <p>从桌面拖入文件，系统会逐页做多轮交叉印证、提炼画像、构建知识网络。</p>
          <p class="welcome-sub">点击左侧「工作台」查看全局关联网络，或选择文件查看详情。</p>
        </div>
      </div>

      <!-- 选中文件：详情 -->
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
            <button class="ghost-btn" title="询问 AI" @click="askAI">🤖 问 AI</button>
            <select v-model="exportFormat" class="export-select" :disabled="!canExport || exporting">
              <option value="markdown">Markdown</option>
              <option value="html">HTML</option>
              <option value="json">JSON</option>
            </select>
            <button class="ghost-btn" :disabled="exporting" @click="handleExport">{{ exporting ? '导出中…' : '导出' }}</button>
            <button class="primary-btn" :disabled="analyzing || sourceUnavailable" @click="startAnalyze">{{ analyzeButtonText }}</button>
            <button class="ghost-btn danger" @click="removeDocument">删除</button>
          </div>
          <div v-if="analyzing" class="head-progress">
            <span class="hp-text">{{ progress?.current_stage || '分析中' }} · {{ overallPercent }}%</span>
            <span class="hp-bar"><span class="hp-fill" :style="{ width: overallPercent + '%' }"></span></span>
          </div>
        </header>

        <section v-if="showProgress" class="progress-panel">
          <div class="pp-top">
            <div class="pp-ring" :style="ringStyle">
              <span class="pp-ring-num">{{ progress?.overall_percent ?? 0 }}<i>%</i></span>
            </div>
            <div class="pp-top-text">
              <div class="pp-stage">{{ progressHeadline }}</div>
              <div class="pp-hint">{{ progressHint }}</div>
            </div>
          </div>
          <ol class="pp-steps">
            <li v-for="s in progress?.stages || []" :key="s.key" class="pp-step" :class="s.status">
              <span class="pp-dot"><template v-if="s.status === 'done'">✓</template><template v-else-if="s.status === 'running'">●</template><template v-else>○</template></span>
              <span class="pp-label">{{ s.label }}</span>
              <span class="pp-track"><span class="pp-fill" :style="{ width: s.percent + '%' }"></span></span>
              <span class="pp-count">{{ stepCount(s) }}</span>
            </li>
          </ol>
        </section>

        <section v-if="ingestStatus" class="status-panel" :class="{ unavailable: sourceUnavailable }">
          <div class="status-main">
            <span class="status-pill" :class="statusClassForIngest">{{ ingestStatusLabel }}</span>
            <span>{{ ingestStatusHint }}</span>
          </div>
          <div class="status-grid">
            <span>当前阶段：{{ stageLabel(ingestStatus.stage) }}</span>
            <span>可检索：{{ ingestStatus.search_ready ? '是' : '否' }}</span>
            <span>深度分析：{{ ingestStatus.deep_ready ? '已完成' : '未完成' }}</span>
            <span>可导出：{{ canExport ? '是' : '否' }}</span>
            <span>{{ graphSemanticText }}</span>
          </div>
          <div v-if="sourceUnavailable" class="status-help">
            原始文件可能已删除、在回收站、无权限或路径不可用。知识库保留了历史记录，但不能继续深度分析、检索或导出；请重新上传、重新绑定源文件，或删除这条无效记录。
            <div class="status-actions">
              <button class="ghost-btn" @click="guideSourceRestore">重新上传/恢复源文件</button>
              <button class="ghost-btn danger" @click="removeDocument">删除无效记录</button>
            </div>
          </div>
          <div v-else-if="ingestStatus.last_error" class="status-help">
            {{ readableFailure(ingestStatus.last_error) }}
          </div>
        </section>

        <nav v-if="hasResult" class="tabs">
          <button :class="{ active: tab === 'overview' }" @click="tab = 'overview'">概览</button>
          <button :class="{ active: tab === 'reader' }" @click="tab = 'reader'">阅读</button>
          <button :class="{ active: tab === 'relation' }" @click="tab = 'relation'">关联</button>
          <button :class="{ active: tab === 'search' }" @click="tab = 'search'">检索</button>
        </nav>

        <section v-if="hasResult && tab === 'overview'" class="pane">
          <div v-if="resultLoadErrors.profile" class="pane-error" role="alert">
            {{ resultLoadErrors.profile }}
          </div>
          <div v-if="profile" class="profile-grid">
            <div class="pf-card pf-main">
              <div class="pf-tag">{{ profile.doc_type || '资料' }}</div>
              <h3>{{ profile.subject || active.filename }}</h3>
              <p class="pf-summary">{{ profile.doc_summary }}</p>
              <button class="ghost-btn" style="margin-top:8px" @click="askAI">🤖 问 AI 关于此文件</button>
            </div>
            <div v-if="profile.core_conclusions" class="pf-card"><div class="pf-h">核心结论</div><p>{{ profile.core_conclusions }}</p></div>
            <div v-if="profile.applicable_scenarios" class="pf-card"><div class="pf-h">适用场景</div><p>{{ profile.applicable_scenarios }}</p></div>
            <div v-if="profileBusinessTags.length" class="pf-card"><div class="pf-h">业务标签</div><div class="chips"><span v-for="tag,i in profileBusinessTags" :key="i" class="chip">{{ tag }}</span></div></div>
            <div v-if="profileEntities.length" class="pf-card"><div class="pf-h">关键信息</div><div class="chips"><span v-for="e,i in profileEntities" :key="i" class="chip">{{ e.name }}</span></div></div>
            <div v-if="profileChapters.length" class="pf-card pf-wide"><div class="pf-h">内容结构</div><ul class="chapter-list"><li v-for="c,i in profileChapters" :key="i" @click="gotoPage(c.page)"><span class="ch-page">P{{ c.page || '·' }}</span><span class="ch-title">{{ c.title }}</span></li></ul></div>
          </div>
          <div v-else class="empty-tip pad">画像生成中或暂无,完成分析后显示</div>
        </section>

        <section v-if="hasResult && tab === 'reader'" class="pane">
          <div v-if="resultLoadErrors.fusions" class="pane-error" role="alert">
            {{ resultLoadErrors.fusions }}
          </div>
          <article v-for="p in fusions" :key="p.page" :ref="el => setPageRef(p.page, el)" class="page-card">
            <div class="page-head"><span class="page-no">第 {{ p.page }} 页</span><span v-if="p.page_title" class="page-title">{{ p.page_title }}</span><span class="conf" :class="confClass(p.confidence)" :title="'融合置信度'">置信 {{ Math.round((p.confidence||0)*100) }}%</span></div>
            <p class="page-text">{{ p.fused_text }}</p>
            <div v-if="p.conflicts && p.conflicts.length" class="conflict-note">⚠ 多轮识别有 {{ p.conflicts.length }} 处差异,已按多数采信</div>
          </article>
          <div v-if="!fusions.length" class="empty-tip pad">完成分析后显示逐页内容</div>
        </section>

        <section v-if="hasResult && tab === 'relation'" class="pane">
          <div v-if="resultLoadErrors.relations" class="pane-error" role="alert">
            {{ resultLoadErrors.relations }}
          </div>
          <div v-if="relations.length" class="rel-list">
            <div class="rel-hint">这份资料与库中其它资料的关联(系统自动织网):</div>
            <button v-for="r in relations" :key="r.target_document_id" class="rel-card" @click="jumpDoc(r.target_document_id)">
              <span class="rel-name">{{ r.target_filename || ('资料 #'+r.target_document_id) }}</span>
              <span class="rel-bar"><span :style="{ width: relPct(r)+'%' }"></span></span>
              <span class="rel-score">{{ relPct(r) }}% 相关</span>
            </button>
          </div>
          <div v-else class="empty-tip pad">暂无关联。库里有相关资料时会自动建立联系。</div>
        </section>

        <section v-if="hasResult && tab === 'search'" class="pane">
          <div class="search-bar"><input v-model="query" class="search-input" placeholder="搜索全库知识内容…" @keyup.enter="runSearch" /><button class="primary-btn" :disabled="searching" @click="runSearch">{{ searching?'搜索中':'搜索' }}</button></div>
          <div v-if="searched" class="search-hint">在 {{ analyzedDocCount }} 个已分析文件中检索「{{ query }}」</div>
          <article v-for="item in searchResults" :key="item.chunk_id ?? `doc:${item.document_id}`" class="result-card" @click="jumpToSearchResult(item)">
            <div class="result-head">
              <span class="result-doc">{{ item.document_name || docName(item.document_id) }}</span>
              <span class="result-page">{{ item.page ? `第 ${item.page} 页` : '文档命中' }}</span>
            </div>
            <div class="result-meta">
              <span>{{ item.source_file || item.document_name || ('文档 #' + item.document_id) }}</span>
              <span v-if="item.paragraph !== null && item.paragraph !== undefined">段落 {{ item.paragraph }}</span>
              <span>{{ item.retrieval_source || 'hybrid' }} · {{ item.explain?.rrf_score ?? item.rrf_score ?? item.score }}</span>
            </div>
            <div class="result-actions">
              <button type="button" :disabled="!item.source_file_id" @click.stop="openSearchSource(item)">打开</button>
              <button type="button" :disabled="!item.source_file_id" @click.stop="downloadSearchSource(item)">下载</button>
              <button type="button" @click.stop="copySearchReference(item)">复制引用</button>
              <button type="button" @click.stop="showSearchMetadata(item)">metadata</button>
            </div>
            <p v-html="highlightText(item.text, query)"></p>
          </article>
          <pre v-if="searchMetadataText" class="result-metadata">{{ searchMetadataText }}</pre>
          <div v-if="searched && !searchResults.length" class="empty-tip pad">没找到相关内容</div>
        </section>
      </template>
    </main>

    <!-- 重新分析确认弹窗 -->
    <div v-if="showRedoDialog" class="redo-overlay" @click.self="showRedoDialog = false">
      <div class="redo-dialog">
        <div class="redo-head">
          <p class="redo-title">重新分析</p>
          <button class="redo-close" @click="confirmRedo(false)">✕</button>
        </div>
        <p class="redo-body">将重跑 LLM 分析层（画像 / 图谱 / 关联）。<br/>是否同时重跑固化数据层（原始采集 + 融合）？</p>
        <div class="redo-actions">
          <button class="redo-force" @click="confirmRedo(true)">重跑</button>
          <button class="redo-skip" @click="confirmRedo(false)">跳过</button>
        </div>
      </div>
    </div>
    </MacAppShell>
  </div>
</template>

<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
import { MacAppShell } from '@/desktop/app-kit'
import { ChartNoAxesCombined, ChevronRight, CircleCheck, Files, FolderSearch, LayoutDashboard, LoaderCircle, TriangleAlert } from '@/shared/icons/lucide'
import { useKnowledgeWorkspace } from './composables/useKnowledgeWorkspace'
import type { KnowledgeEntryProps } from './types'

const DashboardView = defineAsyncComponent(() => import('./views/DashboardView.vue'))

const props = defineProps<KnowledgeEntryProps>()

const {
  documents,
  active,
  showWorkspace,
  showDashboard,
  isAdminOrEditor,
  activeId,
  keyword,
  tab,
  showGovernanceFromPayload,
  fileTree,
  treeLoading,
  treeError,
  visibleTree,
  toggleFolder,
  openWorkspace,
  openDashboard,
  jumpToFirstRunning,
  progress,
  ingestStatus,
  fusions,
  profile,
  relations,
  resultLoadErrors,
  query,
  searching,
  searched,
  searchResults,
  searchMetadataText,
  exportFormat,
  exporting,
  analyzing,
  analyzeButtonText,
  runningCount,
  hasResult,
  showProgress,
  headStatusText,
  progressHeadline,
  progressHint,
  ringStyle,
  overallPercent,
  sourceUnavailable,
  canExport,
  graphSemanticText,
  ingestStatusLabel,
  statusClassForIngest,
  ingestStatusHint,
  profileEntities,
  profileChapters,
  profileBusinessTags,
  fileIcon,
  docName,
  statusDotClass,
  stageLabel,
  readableFailure,
  stepCount,
  confClass,
  relPct,
  analyzedDocCount,
  failedDocumentCount,
  pendingDocumentCount,
  recentDocuments,
  documentStatus,
  documentStatusText,
  highlightText,
  openSearchSource,
  downloadSearchSource,
  copySearchReference,
  showSearchMetadata,
  jumpToSearchResult,
  loadFileTree,
  openDocByNode,
  openDocument,
  startAnalyze,
  handleExport,
  guideSourceRestore,
  showRedoDialog,
  confirmRedo,
  removeDocument,
  runSearch,
  setPageRef,
  gotoPage,
  jumpDoc,
  askAI,
} = useKnowledgeWorkspace(props)
</script>

<style scoped>
.kb-app { height: 100%; min-height: 0; color: var(--mac-app-text); background: var(--mac-app-surface); font: var(--mac-app-font); }
.kb-toolbar { display:grid; gap:1px; min-height: var(--mac-app-toolbar-height); align-content:center; padding:0 4px; width:100%; }
.kb-toolbar-copy strong { font: var(--mac-app-font-title); color: var(--mac-app-text); }
.kb-toolbar-copy span { font: var(--mac-app-font-caption); color: var(--mac-app-text-secondary); }

/* 左侧 */
.kb-side { display: flex; flex-direction: column; gap: 8px; padding: 12px; background: transparent; min-width: 0; height: 100%; box-sizing: border-box; }

.ws-btn { width: 100%; padding: 9px 10px; border: 0; border-radius: var(--mac-app-radius-control); background: transparent; cursor: pointer; font-size: 13px; font-weight: 600; color: var(--mac-app-text-secondary); text-align: left; display: flex; align-items: center; gap: 8px; }
.ws-btn:hover { color: var(--mac-app-accent); background: color-mix(in srgb, var(--mac-app-accent) 8%, transparent); }
.ws-btn.active { color: var(--mac-app-accent); background: var(--mac-app-selection); font-weight: 700; }

.search-mini { height: 34px; padding: 0 12px; border: 1px solid var(--mac-app-border-strong); border-radius: var(--mac-app-radius-control); background: #fff; color: var(--mac-app-text); outline: none; }
.search-mini:focus { border-color: var(--mac-app-accent); }

.running-hint { padding: 8px 10px; margin: 0; border-radius: 8px; background: #fef7e0; border: 1px solid #f0d78c; color: #8b6914; font-size: 12px; font-weight: 600; cursor: pointer; text-align: center; user-select: none; }
.running-hint:hover { background: #fdf0c8; border-color: #e0b84c; }

.tree-wrap { flex: 1; min-height: 0; overflow: auto; }
.tree-error {
  margin: 6px 0;
  padding: 10px;
  border: 1px solid #f1b6ae;
  border-radius: 8px;
  background: #fff7f6;
  color: #b42318;
  display: grid;
  gap: 8px;
  font-size: 12px;
}
.tree-error button {
  justify-self: start;
  height: 28px;
  border: 1px solid currentColor;
  border-radius: 6px;
  background: #fff;
  color: inherit;
  cursor: pointer;
}
.tree-node { display: flex; align-items: center; gap: 4px; width: 100%; padding: 5px 6px; text-align: left; cursor: pointer; border: none; background: transparent; font-size: 12px; color: var(--mac-app-text-secondary); border-radius: var(--mac-app-radius-control); }
.tree-node:hover { background: color-mix(in srgb, var(--mac-app-accent) 8%, transparent); }
.tree-node.active { background: var(--mac-app-selection); color: var(--mac-app-accent); font-weight: 600; }
.tree-arrow { font-size: 8px; width: 10px; flex: none; color: #8aa0b5; }
.tree-icon { font-size: 14px; flex: none; }
.tree-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; }
.tree-dot { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.tree-dot.ok { background: #2bb673; }
.tree-dot.busy { background: #f0b240; animation: pulse 1s infinite; }
.tree-dot.failed { background: #e5534b; }
.tree-dot.warn { background: #f0b240; }
.tree-dot.idle { background: #c2cdda; }
.tree-pct { font-size: 10px; font-weight: 700; color: #f0941f; }
@keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: .35; } }

/* 主区 */
.kb-main { display: flex; flex-direction: column; min-width: 0; padding: 18px 20px; gap: 14px; overflow: hidden; height: 100%; background: transparent; box-sizing: border-box; }

.workspace-overview { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 18px; }
.workspace-head {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 10px 12px; margin-bottom: 4px;
  border-bottom: .5px solid rgba(60,60,67,.12);
  background: color-mix(in srgb, var(--glass-panel-bg, rgba(246,246,250,.66)) 88%, white);
  border-radius: 12px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,.5);
  backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
  -webkit-backdrop-filter: var(--desktop-lg-filter-soft, blur(24px) saturate(160%));
}
.workspace-head h1 { margin: 0; color: #1d1d1f; font-size: 22px; font-weight: 700; }
.workspace-head p { margin: 4px 0 0; color: #8e8e93; font-size: 12px; }
.workspace-head .ghost-btn { display: inline-flex; align-items: center; gap: 6px; }
.workspace-stats { display: grid; grid-template-columns: repeat(auto-fit,minmax(118px,1fr)); gap: 10px; }
.stat-item { min-height: 92px; display: grid; grid-template-columns: 24px 1fr; grid-template-rows: 1fr auto; align-items: center; gap: 0 8px; padding: 14px; border: .5px solid rgba(60,60,67,.16); border-radius: 8px; background: rgba(255,255,255,.92); color: #636366; }
.stat-item svg { grid-row: 1 / 3; color: #0a84ff; }
.stat-item strong { color: #1d1d1f; font-size: 24px; line-height: 1; }
.stat-item span { color: #8e8e93; font-size: 11px; }
.stat-item.is-success svg { color: #28a745; }
.stat-item.is-running svg { color: #ff9f0a; }
.stat-item.is-warning svg { color: #ff453a; }
.recent-section { min-height: 0; padding: 0; }
.section-title { display: flex; align-items: end; justify-content: space-between; margin-bottom: 8px; }
.section-title h2 { margin: 0; color: #1d1d1f; font-size: 14px; }
.section-title span { color: #8e8e93; font-size: 11px; }
.recent-list { overflow: hidden; border: .5px solid rgba(60,60,67,.16); border-radius: 8px; background: #fff; }
.recent-row { width: 100%; min-height: 54px; display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 0; border-bottom: .5px solid rgba(60,60,67,.12); background: transparent; text-align: left; cursor: pointer; }
.recent-row:last-child { border-bottom: 0; }
.recent-row:hover { background: rgba(10,132,255,.06); }
.recent-icon { width: 28px; font-size: 20px; text-align: center; }
.recent-copy { min-width: 0; flex: 1; display: grid; gap: 2px; }
.recent-copy strong { overflow: hidden; color: #1d1d1f; font-size: 12px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.recent-copy small { color: #8e8e93; font-size: 10px; }
.document-state { flex: none; padding: 3px 7px; border-radius: 999px; background: #f2f2f7; color: #636366; font-size: 10px; }
.document-state.done { background: rgba(52,199,89,.12); color: #248a3d; }
.document-state.running { background: rgba(255,159,10,.14); color: #9a6700; }
.document-state.failed, .document-state.source_unavailable { background: rgba(255,69,58,.12); color: #d70015; }
.workspace-empty { min-height: 180px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: #8e8e93; }
.workspace-empty strong { color: #3a3a3c; font-size: 13px; }
.workspace-empty span { font-size: 11px; }
.spin { animation: spin .9s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }


.main-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 6px 16px; padding-bottom: 12px; border-bottom: 1px solid #e3e9f2; position: relative; }
.head-left { display: flex; align-items: center; gap: 12px; min-width: 0; }
.head-ico { font-size: 30px; }
.main-head h2 { margin: 0; font-size: 18px; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.head-meta { font-size: 12px; color: #7c8da0; }
.head-actions { display: flex; gap: 8px; flex: none; }

.head-progress { width: 100%; display: flex; align-items: center; gap: 10px; padding: 4px 0 0; }
.hp-text { font-size: 11px; color: #2395bc; font-weight: 600; white-space: nowrap; flex: none; }
.hp-bar { flex: 1; height: 4px; border-radius: 2px; background: #e6eef5; overflow: hidden; }
.hp-fill { display: block; height: 100%; background: linear-gradient(90deg, #2395bc, #31a1c6); border-radius: 2px; transition: width .4s ease; }

.primary-btn { height: 36px; padding: 0 18px; border: none; border-radius: 8px; cursor: pointer; background: #2395bc; color: #fff; font-weight: 600; font-size: 13px; }
.primary-btn:hover { background: #1f86a9; }
.primary-btn:disabled { background: #aebfcc; cursor: not-allowed; }
.ghost-btn { height: 36px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; cursor: pointer; }
.ghost-btn:hover { border-color: #bcd6e6; }
.ghost-btn:disabled { color: #aab8c6; background: #f5f7fa; cursor: not-allowed; }
.ghost-btn.danger:hover { border-color: #e5534b; color: #e5534b; }
.export-select { height: 36px; border: 1px solid #d5dfeb; border-radius: 8px; background: #fff; color: #46586b; padding: 0 8px; outline: none; }
.export-select:disabled { color: #aab8c6; background: #f5f7fa; }

.progress-panel { border: 1px solid #e3e9f2; border-radius: 14px; background: #fff; padding: 20px; box-shadow: 0 2px 10px rgba(35,149,188,.05); }
.pp-top { display: flex; align-items: center; gap: 18px; margin-bottom: 18px; }
.pp-ring { width: 76px; height: 76px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; position: relative; }
.pp-ring::before { content: ''; position: absolute; width: 56px; height: 56px; border-radius: 50%; background: #fff; }
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
.pp-fill { display: block; height: 100%; background: linear-gradient(90deg,#2395bc,#31a1c6); border-radius: 4px; transition: width .4s ease; }
.pp-step.done .pp-fill { background: #2bb673; }
.pp-count { font-size: 12px; font-weight: 600; color: #5a6b7d; text-align: right; }

.status-panel { border: 1px solid #d5dfeb; border-radius: 12px; background: #fff; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
.status-panel.unavailable { border-color: #f1b6ae; background: #fff7f6; }
.status-main { display: flex; align-items: center; gap: 10px; color: #46586b; font-size: 13px; }
.status-pill { flex: none; padding: 3px 10px; border-radius: 999px; background: #eef2f7; color: #5a6b7d; font-size: 12px; font-weight: 800; }
.status-pill.ok { background: #e3f6ec; color: #1f9d5b; }
.status-pill.busy { background: #fdf2dd; color: #c5851a; }
.status-pill.warn { background: #fff0d9; color: #b45309; }
.status-pill.err { background: #fbe9e7; color: #d4544b; }
.status-grid { display: flex; flex-wrap: wrap; gap: 8px 14px; font-size: 12px; color: #7c8da0; }
.status-help { font-size: 12px; line-height: 1.65; color: #8a4b11; }
.status-actions { margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap; }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid #e3e9f2; flex: none; }
.tabs button { height: 38px; padding: 0 18px; border: none; background: transparent; color: #5a6b7d; cursor: pointer; font-size: 14px; border-radius: 8px 8px 0 0; }
.tabs button:hover { color: #2395bc; }
.tabs button.active { color: #2395bc; font-weight: 700; box-shadow: inset 0 -2px 0 #2395bc; }

.pane { flex: 1; min-height: 0; overflow: auto; }
.pane-error {
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid #f1b6ae;
  border-radius: 8px;
  background: #fff7f6;
  color: #b42318;
  font-size: 13px;
}

.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.pf-card { border: 1px solid #e3e9f2; border-radius: 12px; background: #fff; padding: 16px; }
.pf-main { grid-column: 1 / -1; background: linear-gradient(135deg,#f0f9fd,#eaf6fb); border-color: #cfe7f1; }
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

.rel-hint { font-size: 13px; color: #5a6b7d; margin-bottom: 12px; }
.rel-list { display: flex; flex-direction: column; gap: 10px; }
.rel-card { display: grid; grid-template-columns: 1fr 160px 80px; align-items: center; gap: 12px; width: 100%; padding: 12px 14px; border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; cursor: pointer; text-align: left; }
.rel-card:hover { border-color: #2395bc; background: #f7fbfe; }
.rel-name { font-weight: 600; color: #1c3a4a; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rel-bar { height: 8px; border-radius: 4px; background: #eef2f7; overflow: hidden; }
.rel-bar span { display: block; height: 100%; background: linear-gradient(90deg,#2395bc,#31a1c6); }
.rel-score { font-size: 12px; font-weight: 700; color: #2395bc; text-align: right; }

.search-bar { display: flex; gap: 8px; margin-bottom: 14px; }
.search-input { flex: 1; height: 38px; padding: 0 14px; border: 1px solid #d5dfeb; border-radius: 8px; outline: none; }
.search-input:focus { border-color: #2395bc; }
.result-card { border: 1px solid #e3e9f2; border-radius: 10px; background: #fff; padding: 14px; margin-bottom: 10px; cursor: pointer; }
.result-card:hover { border-color: #2395bc; }
.result-head { display: flex; justify-content: space-between; font-size: 12px; color: #7c8da0; margin-bottom: 8px; gap: 10px; }
.result-doc { font-weight: 600; color: #2395bc; }
.result-meta { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 8px; color: #6b7b8c; font-size: 11px; }
.result-actions { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.result-actions button { height: 24px; padding: 0 8px; border: 1px solid #c8d6e3; border-radius: 6px; background: #fff; color: #365468; font-size: 11px; cursor: pointer; }
.result-actions button:disabled { cursor: default; opacity: 0.45; }
.result-card p { margin: 0; line-height: 1.7; color: #2a3a48; }
.result-metadata { max-height: 220px; overflow: auto; margin: 0 0 10px; padding: 10px; border: 1px solid #d8e5ee; border-radius: 8px; background: #f7fafc; color: #2a3a48; font-size: 11px; white-space: pre-wrap; }
.kw-highlight { background: #fef3c7; color: #92400e; padding: 0 2px; border-radius: 2px; }
.search-hint { font-size: 12px; color: #8aa0b5; margin-bottom: 12px; }

.empty-tip { color: #9aabbd; font-size: 13px; text-align: center; padding: 14px; }
.empty-tip.pad { padding: 40px; }

/* 重新分析弹窗 */
.redo-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.25); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.redo-dialog { background: #fff; border-radius: 14px; padding: 28px 32px; min-width: 360px; max-width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,0.15); }
.redo-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.redo-title { margin: 0; font-size: 17px; font-weight: 700; color: #1c3a4a; }
.redo-close { border: none; background: none; cursor: pointer; font-size: 16px; color: #8aa0b5; padding: 2px 4px; border-radius: 4px; }
.redo-close:hover { color: #46586b; background: #f0f2f5; }
.redo-body { margin: 0 0 24px; font-size: 14px; color: #5a6b7d; line-height: 1.7; }
.redo-actions { display: flex; gap: 10px; justify-content: flex-end; }
.redo-skip { height: 36px; padding: 0 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #2bb673; color: #fff; }
.redo-skip:hover { background: #239a5d; }
.redo-force { height: 36px; padding: 0 20px; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; font-weight: 600; background: #e5534b; color: #fff; }
.redo-force:hover { background: #c94039; }
</style>
