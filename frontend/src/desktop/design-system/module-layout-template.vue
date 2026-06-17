<template>
  <div class="layout-reference">
    <h2 class="layout-reference-title">模块布局模板参考（6 种原型）</h2>
    <div class="layout-switcher">
      <el-radio-group v-model="currentLayout" size="small">
        <el-radio-button value="managementTable">1.managementTable</el-radio-button>
        <el-radio-button value="documentEditor">2.documentEditor</el-radio-button>
        <el-radio-button value="chatApp">3.chatApp</el-radio-button>
        <el-radio-button value="searchApp">4.searchApp</el-radio-button>
        <el-radio-button value="fileManager">5.fileManager</el-radio-button>
        <el-radio-button value="statusDashboard">6.statusDashboard</el-radio-button>
      </el-radio-group>
    </div>
    <section v-if="currentLayout === 'managementTable'" class="layout-example">
      <h3>managementTable</h3>
      <p class="layout-description">适用于用户管理、应用管理等。使用 AppWindowFrame layout="management" 包裹，搭配 AppToolbar。空/错/加载状态使用 AppEmptyState / AppErrorState。</p>
      <div class="layout-management-table">
        <AppToolbar variant="table">
          <el-input placeholder="搜索…" size="small" style="width:200px" />
          <el-button size="small" type="primary">新增</el-button>
          <el-button size="small">导出</el-button>
        </AppToolbar>
        <div class="layout-table-content">
          <el-table :data="[]" stripe size="small">
            <el-table-column prop="name" label="名称" />
            <el-table-column prop="status" label="状态" width="100" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default><el-button size="small" text>编辑</el-button></template>
            </el-table-column>
          </el-table>
          <el-pagination background layout="prev,pager,next" :total="100" small />
        </div>
      </div>
    </section>
    <section v-if="currentLayout === 'documentEditor'" class="layout-example">
      <h3>documentEditor</h3>
      <p class="layout-description">适用于文件预览、文本编辑。使用 AppWindowFrame layout="editor"，内容区 flex:1 独立滚动，AppStatusBar 置于底部。</p>
      <div class="layout-document-editor">
        <AppToolbar variant="editor">toolbar-slot</AppToolbar>
        <div class="editor-content">主编辑区域 · 独立滚动</div>
        <AppStatusBar>字数 0 | 已保存</AppStatusBar>
      </div>
    </section>
    <section v-if="currentLayout === 'chatApp'" class="layout-example">
      <h3>chatApp</h3>
      <p class="layout-description">适用于 AI 助手、客服聊天。使用 AppWindowFrame layout="chat"，侧栏可折叠（过渡动画 0.22s ease），message-list向上滚动，input-area固定底部。</p>
      <div class="layout-chat-app">
        <aside class="chat-sidebar" :style="{ width: sidebarCollapsed ? '0' : '160px' }">
          <div class="sidebar-header">会话列表</div>
        </aside>
        <main class="chat-main">
          <div class="message-list">消息列表 · 向上滚动加载</div>
          <div class="input-area">底部固定输入框</div>
        </main>
      </div>
    </section>
    <section v-if="currentLayout === 'searchApp'" class="layout-example">
      <h3>searchApp</h3>
      <p class="layout-description">适用于内容库、文件工具箱。使用 AppWindowFrame layout="search"，search-bar居顶，分类筛选左侧，详情右侧 el-drawer 30% 滑入。</p>
      <div class="layout-search-app">
        <div class="search-bar"><el-input placeholder="搜索内容…" clearable size="small" /></div>
        <div class="search-main">
          <aside class="search-filter">分类筛选</aside>
          <div class="search-results">结果列表 · 表格或卡片网格</div>
          <aside class="detail-drawer">detail-drawer · 右侧滑入</aside>
        </div>
      </div>
    </section>
    <section v-if="currentLayout === 'fileManager'" class="layout-example">
      <h3>fileManager</h3>
      <p class="layout-description">适用于文件管理。使用 AppWindowFrame layout="file-manager"，tree-sidebar可折叠 240px，toolbar-slot含面包屑导航，右侧可选preview-panel。</p>
      <div class="layout-file-manager">
        <aside class="tree-sidebar">目录树 · 可折叠</aside>
        <div class="file-main">
          <AppToolbar variant="table">
            <el-breadcrumb><el-breadcrumb-item>根目录</el-breadcrumb-item></el-breadcrumb>
            <div><el-button size="small" text>网格</el-button><el-button size="small" text>列表</el-button></div>
          </AppToolbar>
          <div class="file-content">拖拽上传区域 / 网格视图</div>
        </div>
        <aside class="preview-panel">preview-panel（可选）</aside>
      </div>
    </section>
    <section v-if="currentLayout === 'statusDashboard'" class="layout-example">
      <h3>statusDashboard</h3>
      <p class="layout-description">适用于仪表盘、系统状态。使用 AppWindowFrame layout="dashboard"，metric-card 4 列弹性网格，中段图表与表格并排，底部activity-stream。</p>
      <div class="layout-status-dashboard">
        <div class="metric-row">
          <div class="metric-card">指标1</div>
          <div class="metric-card">指标2</div>
          <div class="metric-card">指标3</div>
          <div class="metric-card">指标4</div>
        </div>
        <div class="dashboard-middle">
          <div class="dashboard-chart">图表区域</div>
          <div class="dashboard-table">表格区域</div>
        </div>
        <div class="activity-stream">activity-stream · {{ new Date().toLocaleTimeString() }} 更新</div>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AppToolbar from '@/desktop/components/app-toolbar.vue'
import AppStatusBar from '@/desktop/components/app-status-bar.vue'
const currentLayout = ref('managementTable')
const sidebarCollapsed = ref(false)
</script>
<style scoped>
.layout-reference { padding: 20px; color: var(--text-primary); font-family: var(--font-stack); }
.layout-reference-title { margin-bottom: 16px; font-size: 18px; font-weight: 600; }
.layout-switcher { margin-bottom: 16px; }
.layout-example { padding: 16px; border: 1px solid var(--border-color); border-radius: var(--radius-md); background: var(--card-bg); }
.layout-example h3 { margin: 0 0 4px; font-size: 14px; color: var(--text-secondary); }
.layout-description { margin: 0 0 12px; font-size: 12px; color: var(--text-muted); line-height: 1.5; }
.layout-example [class*="area"],.layout-example [class*="bar"],.layout-example [class*="card"],.layout-example [class*="panel"],.layout-example [class*="content"],.layout-example [class*="sidebar"] {
  background: var(--page-bg); border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--text-placeholder); }
.layout-management-table { display: flex; flex-direction: column; gap: 8px; }
.layout-management-table .toolbar-slot { display: flex; gap: 8px; align-items: center; }
.layout-management-table .el-pagination { justify-content: center; }
.layout-document-editor { display: flex; flex-direction: column; gap: 4px; height: 160px; }
.layout-document-editor .editor-toolbar { height: 32px; flex-shrink: 0; }
.layout-document-editor .editor-content { flex: 1; overflow: auto; }
.layout-document-editor .editor-statusbar { height: 24px; flex-shrink: 0; font-size: 11px; color: var(--text-muted); }
.layout-chat-app { display: flex; gap: 8px; height: 180px; }
.layout-chat-app .chat-sidebar { flex-shrink: 0; overflow: hidden; transition: width 0.3s; display: flex; flex-direction: column; gap: 4px; }
.layout-chat-app .chat-main { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.layout-chat-app .message-list { flex: 1; overflow-y: auto; }
.layout-chat-app .input-area { height: 40px; flex-shrink: 0; }
.layout-search-app { display: flex; flex-direction: column; gap: 8px; height: 160px; }
.layout-search-app .search-bar { flex-shrink: 0; }
.layout-search-app .search-main { flex: 1; display: flex; gap: 8px; }
.layout-search-app .search-filter { width: 100px; flex-shrink: 0; }
.layout-search-app .search-results { flex: 1; }
.layout-search-app .detail-drawer { width: 160px; flex-shrink: 0; }
.layout-file-manager { display: flex; gap: 8px; height: 170px; }
.layout-file-manager .tree-sidebar { width: 100px; flex-shrink: 0; }
.layout-file-manager .file-main { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.layout-file-manager .file-toolbar { height: 28px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 0 8px; }
.layout-file-manager .file-content { flex: 1; }
.layout-file-manager .preview-panel { width: 100px; flex-shrink: 0; }
.layout-status-dashboard { display: flex; flex-direction: column; gap: 8px; }
.layout-status-dashboard .metric-row { display: flex; gap: 8px; }
.layout-status-dashboard .metric-card { flex: 1; height: 44px; }
.layout-status-dashboard .dashboard-middle { display: flex; gap: 8px; height: 80px; }
.layout-status-dashboard .dashboard-chart, .dashboard-table { flex: 1; }
.layout-status-dashboard .activity-stream { height: 36px; font-size: 11px; color: var(--text-muted); }
</style>
