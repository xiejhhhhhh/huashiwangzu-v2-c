<template>
  <div class="布局参考">
    <h2 class="布局参考-标题">模块布局模板参考（6 种原型）</h2>
    <div class="布局切换">
      <el-radio-group v-model="当前布局" size="small">
        <el-radio-button value="管理表格">1.管理表格</el-radio-button>
        <el-radio-button value="文档编辑器">2.文档编辑器</el-radio-button>
        <el-radio-button value="聊天应用">3.聊天应用</el-radio-button>
        <el-radio-button value="知识搜索">4.知识搜索</el-radio-button>
        <el-radio-button value="文件管理器">5.文件管理器</el-radio-button>
        <el-radio-button value="状态仪表盘">6.状态仪表盘</el-radio-button>
      </el-radio-group>
    </div>
    <section v-if="当前布局 === '管理表格'" class="布局示例">
      <h3>管理表格</h3>
      <p class="布局说明">适用于用户管理、应用管理等。使用 AppWindowFrame layout="management" 包裹，搭配 AppToolbar。空/错/加载状态使用 AppEmptyState / AppErrorState。</p>
      <div class="L-管理表格">
        <AppToolbar variant="table">
          <el-input placeholder="搜索…" size="small" style="width:200px" />
          <el-button size="small" type="primary">新增</el-button>
          <el-button size="small">导出</el-button>
        </AppToolbar>
        <div class="L-表格内容">
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
    <section v-if="当前布局 === '文档编辑器'" class="布局示例">
      <h3>文档编辑器</h3>
      <p class="布局说明">适用于文件预览、文本编辑。使用 AppWindowFrame layout="editor"，内容区 flex:1 独立滚动，AppStatusBar 置于底部。</p>
      <div class="L-文档编辑器">
        <AppToolbar variant="editor">工具栏</AppToolbar>
        <div class="编辑内容区">主编辑区域 · 独立滚动</div>
        <AppStatusBar>字数 0 | 已保存</AppStatusBar>
      </div>
    </section>
    <section v-if="当前布局 === '聊天应用'" class="布局示例">
      <h3>聊天应用</h3>
      <p class="布局说明">适用于 AI 助手、客服聊天。使用 AppWindowFrame layout="chat"，侧栏可折叠（过渡动画 0.22s ease），消息区向上滚动，输入区固定底部。</p>
      <div class="L-聊天应用">
        <aside class="聊天侧栏" :style="{ width: 侧栏折叠 ? '0' : '160px' }">
          <div class="侧栏头部">会话列表</div>
        </aside>
        <main class="聊天主体">
          <div class="消息区">消息列表 · 向上滚动加载</div>
          <div class="输入区">底部固定输入框</div>
        </main>
      </div>
    </section>
    <section v-if="当前布局 === '知识搜索'" class="布局示例">
      <h3>知识搜索</h3>
      <p class="布局说明">适用于知识库、文件工具箱。使用 AppWindowFrame layout="search"，搜索栏居顶，分类筛选左侧，详情右侧 el-drawer 30% 滑入。</p>
      <div class="L-知识搜索">
        <div class="搜索栏"><el-input placeholder="搜索知识库…" clearable size="small" /></div>
        <div class="搜索主体">
          <aside class="搜索筛选">分类筛选</aside>
          <div class="搜索结果">结果列表 · 表格或卡片网格</div>
          <aside class="详情抽屉">详情抽屉 · 右侧滑入</aside>
        </div>
      </div>
    </section>
    <section v-if="当前布局 === '文件管理器'" class="布局示例">
      <h3>文件管理器</h3>
      <p class="布局说明">适用于文件管理。使用 AppWindowFrame layout="file-manager"，树侧栏可折叠 240px，工具栏含面包屑导航，右侧可选预览面板。</p>
      <div class="L-文件管理器">
        <aside class="树侧栏">目录树 · 可折叠</aside>
        <div class="文件主区">
          <AppToolbar variant="table">
            <el-breadcrumb><el-breadcrumb-item>根目录</el-breadcrumb-item></el-breadcrumb>
            <div><el-button size="small" text>网格</el-button><el-button size="small" text>列表</el-button></div>
          </AppToolbar>
          <div class="文件内容">拖拽上传区域 / 网格视图</div>
        </div>
        <aside class="预览面板">预览面板（可选）</aside>
      </div>
    </section>
    <section v-if="当前布局 === '状态仪表盘'" class="布局示例">
      <h3>状态仪表盘</h3>
      <p class="布局说明">适用于仪表盘、系统状态。使用 AppWindowFrame layout="dashboard"，统计卡片 4 列弹性网格，中段图表与表格并排，底部活动流。</p>
      <div class="L-状态仪表盘">
        <div class="统计行">
          <div class="统计卡片">指标1</div>
          <div class="统计卡片">指标2</div>
          <div class="统计卡片">指标3</div>
          <div class="统计卡片">指标4</div>
        </div>
        <div class="仪表盘中段">
          <div class="仪表盘图表">图表区域</div>
          <div class="仪表盘表格">表格区域</div>
        </div>
        <div class="活动流">活动流 · {{ new Date().toLocaleTimeString() }} 更新</div>
      </div>
    </section>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import AppToolbar from '@/desktop/components/app-toolbar.vue'
import AppStatusBar from '@/desktop/components/app-status-bar.vue'
const 当前布局 = ref('管理表格')
const 侧栏折叠 = ref(false)
</script>
<style scoped>
.布局参考 { padding: 20px; color: var(--文字主色); font-family: var(--字体栈); }
.布局参考-标题 { margin-bottom: 16px; font-size: 18px; font-weight: 600; }
.布局切换 { margin-bottom: 16px; }
.布局示例 { padding: 16px; border: 1px solid var(--边框色); border-radius: var(--圆角中); background: var(--卡片背景); }
.布局示例 h3 { margin: 0 0 4px; font-size: 14px; color: var(--文字次要); }
.布局说明 { margin: 0 0 12px; font-size: 12px; color: var(--文字信息); line-height: 1.5; }
.布局示例 [class*="区"],.布局示例 [class*="栏"],.布局示例 [class*="卡片"],.布局示例 [class*="面板"] {
  background: var(--背景色); border-radius: var(--圆角小); display: flex; align-items: center; justify-content: center; font-size: 12px; color: var(--文字占位); }
.L-管理表格 { display: flex; flex-direction: column; gap: 8px; }
.L-管理表格 .工具栏 { display: flex; gap: 8px; align-items: center; }
.L-管理表格 .el-pagination { justify-content: center; }
.L-文档编辑器 { display: flex; flex-direction: column; gap: 4px; height: 160px; }
.L-文档编辑器 .编辑器工具栏 { height: 32px; flex-shrink: 0; }
.L-文档编辑器 .编辑内容区 { flex: 1; overflow: auto; }
.L-文档编辑器 .编辑状态栏 { height: 24px; flex-shrink: 0; font-size: 11px; color: var(--文字信息); }
.L-聊天应用 { display: flex; gap: 8px; height: 180px; }
.L-聊天应用 .聊天侧栏 { flex-shrink: 0; overflow: hidden; transition: width 0.3s; display: flex; flex-direction: column; gap: 4px; }
.L-聊天应用 .聊天主体 { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.L-聊天应用 .消息区 { flex: 1; overflow-y: auto; }
.L-聊天应用 .输入区 { height: 40px; flex-shrink: 0; }
.L-知识搜索 { display: flex; flex-direction: column; gap: 8px; height: 160px; }
.L-知识搜索 .搜索栏 { flex-shrink: 0; }
.L-知识搜索 .搜索主体 { flex: 1; display: flex; gap: 8px; }
.L-知识搜索 .搜索筛选 { width: 100px; flex-shrink: 0; }
.L-知识搜索 .搜索结果 { flex: 1; }
.L-知识搜索 .详情抽屉 { width: 160px; flex-shrink: 0; }
.L-文件管理器 { display: flex; gap: 8px; height: 170px; }
.L-文件管理器 .树侧栏 { width: 100px; flex-shrink: 0; }
.L-文件管理器 .文件主区 { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.L-文件管理器 .文件工具栏 { height: 28px; flex-shrink: 0; display: flex; align-items: center; justify-content: space-between; padding: 0 8px; }
.L-文件管理器 .文件内容 { flex: 1; }
.L-文件管理器 .预览面板 { width: 100px; flex-shrink: 0; }
.L-状态仪表盘 { display: flex; flex-direction: column; gap: 8px; }
.L-状态仪表盘 .统计行 { display: flex; gap: 8px; }
.L-状态仪表盘 .统计卡片 { flex: 1; height: 44px; }
.L-状态仪表盘 .仪表盘中段 { display: flex; gap: 8px; height: 80px; }
.L-状态仪表盘 .仪表盘图表, .仪表盘表格 { flex: 1; }
.L-状态仪表盘 .活动流 { height: 36px; font-size: 11px; color: var(--文字信息); }
</style>
