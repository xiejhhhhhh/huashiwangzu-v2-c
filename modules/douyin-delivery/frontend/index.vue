<template>
  <div class="douyin-app">
    <div class="dy-header">
      <h2 class="dy-title">抖音内容与计划助手</h2>
      <div class="dy-channel-tabs">
        <el-radio-group v-model="activeChannel" size="small" @change="onChannelChange">
          <el-radio-button value="local_push">本地推</el-radio-button>
          <el-radio-button value="ocean_engine">巨量引擎</el-radio-button>
          <el-radio-button value="qianchuan">千川</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="dy-tabs" @tab-change="onTabChange">
      <el-tab-pane label="口播脚本" name="scripts">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-input v-model="scriptInput" placeholder="输入产品/卖点方向，如「神经酰胺修护屏障」" clearable style="width:380px" />
            <el-select v-model="scriptGenChannel" style="width:120px">
              <el-option label="本地推" value="local_push" />
              <el-option label="巨量引擎" value="ocean_engine" />
              <el-option label="千川" value="qianchuan" />
            </el-select>
            <el-button type="primary" :loading="scriptLoading" @click="generateScript">生成脚本</el-button>
          </div>
          <div class="toolbar-right">
            <el-select v-model="scriptFilterChannel" placeholder="渠道筛选" clearable style="width:120px" @change="loadScripts">
              <el-option label="本地推" value="local_push" />
              <el-option label="巨量引擎" value="ocean_engine" />
              <el-option label="千川" value="qianchuan" />
            </el-select>
          </div>
        </div>

        <div v-if="scriptResult" class="result-card">
          <div class="result-header">
            <span class="result-label">生成结果</span>
            <div class="result-actions">
              <el-button size="small" @click="saveCurrentScript">保存脚本</el-button>
              <el-button size="small" @click="scriptResult = null">关闭</el-button>
            </div>
          </div>
          <pre class="result-content">{{ scriptResult.script }}</pre>
        </div>

        <div class="list-section">
          <h3>脚本列表</h3>
          <el-alert v-if="scriptsError" type="error" :title="scriptsError" show-icon :closable="false" class="list-error" />
          <el-table :data="scriptsList" stripe style="width:100%" v-loading="scriptsLoading" size="small">
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="channel" label="渠道" width="90">
              <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
            </el-table-column>
            <el-table-column prop="product_name" label="产品" width="120" show-overflow-tooltip />
            <el-table-column prop="status" label="状态" width="80" />
            <el-table-column prop="updated_at" label="更新时间" width="160" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" @click="previewScript(row)">查看</el-button>
                <el-button link size="small" type="danger" @click="deleteScript(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="广告文案" name="ad-copies">
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-input v-model="adCopyInput" placeholder="输入产品/卖点" clearable style="width:300px" />
            <el-select v-model="adCopyChannel" style="width:120px">
              <el-option label="本地推" value="local_push" />
              <el-option label="巨量引擎" value="ocean_engine" />
              <el-option label="千川" value="qianchuan" />
            </el-select>
            <el-select v-model="adCopyType" placeholder="广告类型" style="width:120px">
              <el-option label="信息流" value="feed" />
              <el-option label="搜索广告" value="search" />
              <el-option label="品牌广告" value="brand" />
            </el-select>
            <el-button type="primary" :loading="adCopyLoading" @click="generateAdCopy">生成文案</el-button>
          </div>
        </div>

        <div v-if="adCopyResult" class="result-card">
          <div class="result-header">
            <span class="result-label">生成结果</span>
            <div class="result-actions">
              <el-button size="small" @click="saveCurrentAdCopy">保存文案</el-button>
              <el-button size="small" @click="adCopyResult = null">关闭</el-button>
            </div>
          </div>
          <pre class="result-content">{{ adCopyResult.ad_copy }}</pre>
        </div>

        <div class="list-section">
          <h3>文案列表</h3>
          <el-alert v-if="adCopiesError" type="error" :title="adCopiesError" show-icon :closable="false" class="list-error" />
          <el-table :data="adCopiesList" stripe style="width:100%" v-loading="adCopiesLoading" size="small">
            <el-table-column prop="title" label="标题" min-width="180" show-overflow-tooltip />
            <el-table-column prop="channel" label="渠道" width="90">
              <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
            </el-table-column>
            <el-table-column prop="ad_type" label="类型" width="80" />
            <el-table-column prop="status" label="状态" width="80" />
            <el-table-column prop="updated_at" label="更新时间" width="160" />
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" @click="previewAdCopy(row)">查看</el-button>
                <el-button link size="small" type="danger" @click="deleteAdCopy(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="计划与交接" name="campaigns">
        <div class="tab-toolbar">
          <el-button type="primary" @click="showCampaignForm = true">新建计划草稿</el-button>
        </div>

        <div v-if="showCampaignForm" class="form-card">
          <h3>新建计划草稿</h3>
          <el-form :model="campaignForm" label-width="100px" size="small">
            <el-form-item label="计划名称">
              <el-input v-model="campaignForm.name" />
            </el-form-item>
            <el-form-item label="计划渠道">
              <el-select v-model="campaignForm.channel">
                <el-option label="本地推" value="local_push" />
                <el-option label="巨量引擎" value="ocean_engine" />
                <el-option label="千川" value="qianchuan" />
              </el-select>
            </el-form-item>
            <el-form-item label="预算">
              <el-input-number v-model="campaignForm.budget" :min="0" style="width:200px" />
              <el-select v-model="campaignForm.budget_type" style="width:100px;margin-left:8px">
                <el-option label="日预算" value="daily" />
                <el-option label="总预算" value="total" />
              </el-select>
            </el-form-item>
            <el-form-item label="投放日期">
              <el-date-picker v-model="campaignDateRange" type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" value-format="YYYY-MM-DD" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="campaignForm.notes" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitCampaign">保存</el-button>
              <el-button @click="showCampaignForm = false">取消</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="list-section">
          <h3>计划草稿列表</h3>
          <el-alert v-if="campaignsError" type="error" :title="campaignsError" show-icon :closable="false" class="list-error" />
          <el-table :data="campaignsList" stripe style="width:100%" v-loading="campaignsLoading" size="small">
            <el-table-column prop="name" label="计划名称" min-width="160" show-overflow-tooltip />
            <el-table-column prop="channel" label="渠道" width="90">
              <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
            </el-table-column>
            <el-table-column prop="budget" label="预算" width="100">
              <template #default="{ row }">{{ row.budget ? row.budget + '元' : '-' }}</template>
            </el-table-column>
            <el-table-column prop="status" label="状态" width="90" />
            <el-table-column prop="start_date" label="开始" width="110" />
            <el-table-column prop="end_date" label="结束" width="110" />
            <el-table-column label="操作" width="180" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" @click="analyzeCampaign(row)">分析</el-button>
                <el-button link size="small" @click="editCampaign(row)">编辑</el-button>
                <el-button link size="small" type="danger" @click="deleteCampaign(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div v-if="campaignAnalysis" class="result-card">
          <div class="result-header">
            <span class="result-label">计划分析</span>
            <el-button size="small" @click="campaignAnalysis = null">关闭</el-button>
          </div>
          <pre class="result-content">{{ campaignAnalysis.analysis }}</pre>
        </div>
      </el-tab-pane>

      <el-tab-pane label="产品管理" name="products">
        <div class="tab-toolbar">
          <el-button type="primary" @click="showProductForm = true">添加产品</el-button>
        </div>

        <div v-if="showProductForm" class="form-card">
          <h3>{{ editingProduct ? '编辑产品' : '添加产品' }}</h3>
          <el-form :model="productForm" label-width="100px" size="small">
            <el-form-item label="产品名称">
              <el-input v-model="productForm.name" />
            </el-form-item>
            <el-form-item label="品类">
              <el-input v-model="productForm.category" />
            </el-form-item>
            <el-form-item label="卖点">
              <el-input v-model="productForm.selling_points_text" type="textarea" :rows="2" placeholder="每行一个卖点" />
            </el-form-item>
            <el-form-item label="成分">
              <el-input v-model="productForm.ingredients_text" type="textarea" :rows="2" placeholder="每行一个成分" />
            </el-form-item>
            <el-form-item label="目标人群">
              <el-input v-model="productForm.target_audience" />
            </el-form-item>
            <el-form-item label="品牌">
              <el-input v-model="productForm.brand" />
            </el-form-item>
            <el-form-item label="备注">
              <el-input v-model="productForm.notes" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitProduct">保存</el-button>
              <el-button @click="showProductForm = false; editingProduct = null">取消</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="list-section">
          <el-alert v-if="productsError" type="error" :title="productsError" show-icon :closable="false" class="list-error" />
          <el-table :data="productsList" stripe style="width:100%" v-loading="productsLoading" size="small">
            <el-table-column prop="name" label="产品名称" min-width="160" />
            <el-table-column prop="category" label="品类" width="100" />
            <el-table-column label="卖点" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">{{ row.selling_points?.join('、') || '-' }}</template>
            </el-table-column>
            <el-table-column label="成分" min-width="180" show-overflow-tooltip>
              <template #default="{ row }">{{ row.ingredients?.join('、') || '-' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" @click="editProduct(row)">编辑</el-button>
                <el-button link size="small" type="danger" @click="deleteProduct(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <el-tab-pane label="内容校验" name="validate">
        <div class="tab-toolbar">
          <div class="toolbar-left" style="width:100%;flex-direction:column;gap:8px">
            <el-input v-model="validateInput" type="textarea" :rows="6" placeholder="粘贴需要校验的成分/功效内容..." />
            <el-button type="primary" :loading="validateLoading" @click="doValidate">校验内容</el-button>
          </div>
        </div>

        <div v-if="validateResult" class="result-card" style="margin-top:16px">
          <div class="result-header">
            <span class="result-label">
              校验结果
              <el-tag v-if="validateResult.has_knowledge_base_results" type="success" size="small" style="margin-left:8px">知识库已匹配</el-tag>
              <el-tag v-else type="warning" size="small" style="margin-left:8px">无知识库匹配</el-tag>
            </span>
            <el-button size="small" @click="validateResult = null">关闭</el-button>
          </div>
          <pre class="result-content">{{ validateResult.ai_validation }}</pre>
        </div>
      </el-tab-pane>

      <el-tab-pane label="提示词设置" name="prompts">
        <div class="tab-toolbar">
          <el-button type="primary" @click="showPromptForm = true">新建提示词</el-button>
        </div>

        <div v-if="showPromptForm" class="form-card">
          <h3>编辑提示词</h3>
          <el-form :model="promptForm" label-width="100px" size="small">
            <el-form-item label="Key">
              <el-input v-model="promptForm.key" :disabled="!!editingPrompt" />
            </el-form-item>
            <el-form-item label="名称">
              <el-input v-model="promptForm.name" />
            </el-form-item>
            <el-form-item label="分类">
              <el-select v-model="promptForm.category">
                <el-option label="系统" value="system" />
                <el-option label="脚本" value="script" />
                <el-option label="文案" value="ad_copy" />
                <el-option label="校验" value="validation" />
                <el-option label="渠道说明" value="channel_info" />
                <el-option label="自定义" value="custom" />
              </el-select>
            </el-form-item>
            <el-form-item label="渠道">
              <el-select v-model="promptForm.channel" clearable>
                <el-option label="通用" value="" />
                <el-option label="本地推" value="local_push" />
                <el-option label="巨量引擎" value="ocean_engine" />
                <el-option label="千川" value="qianchuan" />
              </el-select>
            </el-form-item>
            <el-form-item label="内容">
              <el-input v-model="promptForm.content" type="textarea" :rows="10" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="promptForm.description" />
            </el-form-item>
            <el-form-item>
              <el-button type="primary" @click="submitPrompt">保存</el-button>
              <el-button @click="showPromptForm = false; editingPrompt = null">取消</el-button>
            </el-form-item>
          </el-form>
        </div>

        <div class="list-section">
          <el-alert v-if="promptsError" type="error" :title="promptsError" show-icon :closable="false" class="list-error" />
          <el-table :data="promptsList" stripe style="width:100%" v-loading="promptsLoading" size="small">
            <el-table-column prop="key" label="Key" width="160" />
            <el-table-column prop="name" label="名称" min-width="160" />
            <el-table-column prop="category" label="分类" width="80" />
            <el-table-column prop="channel" label="渠道" width="80">
              <template #default="{ row }">{{ row.channel ? channelLabel(row.channel) : '通用' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button link size="small" @click="editPrompt(row)">编辑</el-button>
                <el-button link size="small" type="danger" @click="deletePrompt(row.id)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- Script preview dialog -->
    <el-dialog v-model="showScriptDialog" title="脚本详情" width="700px">
      <div v-if="previewingScript">
        <p><strong>标题：</strong>{{ previewingScript.title }}</p>
        <p><strong>渠道：</strong>{{ channelLabel(previewingScript.channel) }}</p>
        <p><strong>产品：</strong>{{ previewingScript.product_name }}</p>
        <pre class="dialog-content">{{ previewingScript.full_script }}</pre>
        <div v-if="previewingScript.hashtags?.length" style="margin-top:8px">
          <el-tag v-for="tag in previewingScript.hashtags" :key="tag" style="margin:2px">{{ tag }}</el-tag>
        </div>
      </div>
    </el-dialog>

    <!-- Ad copy preview dialog -->
    <el-dialog v-model="showAdCopyDialog" title="文案详情" width="700px">
      <div v-if="previewingAdCopy">
        <p><strong>标题：</strong>{{ previewingAdCopy.title }}</p>
        <p><strong>渠道：</strong>{{ channelLabel(previewingAdCopy.channel) }}</p>
        <p><strong>类型：</strong>{{ previewingAdCopy.ad_type }}</p>
        <p><strong>产品：</strong>{{ previewingAdCopy.product_name }}</p>
        <pre class="dialog-content">{{ previewingAdCopy.description }}</pre>
        <p v-if="previewingAdCopy.target_audience_desc" style="margin-top:8px">
          <strong>定向建议：</strong>{{ previewingAdCopy.target_audience_desc }}
        </p>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { initRuntime } from '../runtime'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as api from './api'

onMounted(() => initRuntime('douyin-delivery'))

const activeTab = ref('scripts')
const activeChannel = ref('local_push')

const channelLabel = (ch: string) => ({ local_push: '本地推', ocean_engine: '巨量引擎', qianchuan: '千川' })[ch] || ch

function onChannelChange() {}
function onTabChange() {}

function errorMessage(e: unknown, fallback: string): string {
  return e instanceof Error && e.message ? e.message : fallback
}

function showLoadError(target: { value: string }, fallback: string, e: unknown) {
  const message = errorMessage(e, fallback)
  target.value = message
  ElMessage.error(message)
}

// ── Script tab ─────────────────────────────────

const scriptInput = ref('')
const scriptGenChannel = ref('local_push')
const scriptFilterChannel = ref('')
const scriptLoading = ref(false)
const scriptResult = ref<api.GenerateResult | null>(null)
const scriptsList = ref<api.Script[]>([])
const scriptsLoading = ref(false)
const scriptsError = ref('')
const showScriptDialog = ref(false)
const previewingScript = ref<api.Script | null>(null)

async function generateScript() {
  if (!scriptInput.value.trim()) {
    ElMessage.warning('请输入产品/卖点')
    return
  }
  scriptLoading.value = true
  try {
    const r = await api.scripts.generate(scriptInput.value.trim(), scriptGenChannel.value)
    scriptResult.value = r
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '生成失败')
  } finally {
    scriptLoading.value = false
  }
}

async function saveCurrentScript() {
  if (!scriptResult.value?.script) return
  try {
    const lines = scriptResult.value.script.split('\n')
    const titleLine = lines.find(l => l.includes('标题') || l.includes('##'))
    const title = titleLine?.replace(/^[#\s]*/, '').slice(0, 100) || scriptInput.value || '未命名脚本'
    await api.scripts.create({
      title,
      product_name: scriptInput.value,
      channel: scriptGenChannel.value,
      full_script: scriptResult.value.script,
      status: 'draft',
    })
    ElMessage.success('脚本已保存')
    await loadScripts()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  }
}

async function loadScripts() {
  scriptsLoading.value = true
  scriptsError.value = ''
  try {
    scriptsList.value = await api.scripts.list(scriptFilterChannel.value || undefined)
  } catch (e: unknown) {
    showLoadError(scriptsError, '脚本列表加载失败', e)
  }
  finally { scriptsLoading.value = false }
}

function previewScript(row: api.Script) {
  previewingScript.value = row
  showScriptDialog.value = true
}

async function deleteScript(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这条脚本吗？')
    await api.scripts.delete(id)
    ElMessage.success('已删除')
    await loadScripts()
  } catch { /* cancelled */ }
}

// ── Ad Copy tab ───────────────────────────────

const adCopyInput = ref('')
const adCopyChannel = ref('ocean_engine')
const adCopyType = ref('feed')
const adCopyLoading = ref(false)
const adCopyResult = ref<api.GenerateResult | null>(null)
const adCopiesList = ref<api.AdCopy[]>([])
const adCopiesLoading = ref(false)
const adCopiesError = ref('')
const showAdCopyDialog = ref(false)
const previewingAdCopy = ref<api.AdCopy | null>(null)

async function generateAdCopy() {
  if (!adCopyInput.value.trim()) {
    ElMessage.warning('请输入产品/卖点')
    return
  }
  adCopyLoading.value = true
  try {
    const r = await api.adCopies.generate(adCopyInput.value.trim(), adCopyChannel.value, adCopyType.value)
    adCopyResult.value = r
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '生成失败')
  } finally {
    adCopyLoading.value = false
  }
}

async function saveCurrentAdCopy() {
  if (!adCopyResult.value?.ad_copy) return
  try {
    await api.adCopies.create({
      title: adCopyInput.value,
      product_name: adCopyInput.value,
      channel: adCopyChannel.value,
      ad_type: adCopyType.value,
      description: adCopyResult.value.ad_copy,
      status: 'draft',
    })
    ElMessage.success('文案已保存')
    await loadAdCopies()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  }
}

async function loadAdCopies() {
  adCopiesLoading.value = true
  adCopiesError.value = ''
  try {
    adCopiesList.value = await api.adCopies.list()
  } catch (e: unknown) {
    showLoadError(adCopiesError, '文案列表加载失败', e)
  }
  finally { adCopiesLoading.value = false }
}

function previewAdCopy(row: api.AdCopy) {
  previewingAdCopy.value = row
  showAdCopyDialog.value = true
}

async function deleteAdCopy(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这条文案吗？')
    await api.adCopies.delete(id)
    ElMessage.success('已删除')
    await loadAdCopies()
  } catch { /* cancelled */ }
}

// ── Campaign tab ─────────────────────────────

const showCampaignForm = ref(false)
const campaignForm = ref({
  name: '',
  channel: 'local_push',
  budget: 0,
  budget_type: 'daily' as string,
  notes: '',
})
const campaignDateRange = ref<[string, string] | null>(null)
const campaignsList = ref<api.Campaign[]>([])
const campaignsLoading = ref(false)
const campaignsError = ref('')
const campaignAnalysis = ref<{ analysis: string } | null>(null)

async function loadCampaigns() {
  campaignsLoading.value = true
  campaignsError.value = ''
  try {
    campaignsList.value = await api.campaigns.list()
  } catch (e: unknown) {
    showLoadError(campaignsError, '计划列表加载失败', e)
  }
  finally { campaignsLoading.value = false }
}

async function submitCampaign() {
  if (!campaignForm.value.name.trim()) {
    ElMessage.warning('请输入计划名称')
    return
  }
  try {
    const data: Partial<api.Campaign> = { ...campaignForm.value }
    if (campaignDateRange.value) {
      data.start_date = campaignDateRange.value[0]
      data.end_date = campaignDateRange.value[1]
    }
    await api.campaigns.create(data)
    ElMessage.success('计划已创建')
    showCampaignForm.value = false
    resetCampaignForm()
    await loadCampaigns()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '创建失败')
  }
}

function resetCampaignForm() {
  campaignForm.value = { name: '', channel: 'local_push', budget: 0, budget_type: 'daily', notes: '' }
  campaignDateRange.value = null
}

async function analyzeCampaign(row: api.Campaign) {
  try {
    const r = await api.campaigns.analyze(row.id)
    campaignAnalysis.value = r
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '分析失败')
  }
}

function editCampaign(row: api.Campaign) {
  campaignForm.value = {
    name: row.name,
    channel: row.channel,
    budget: row.budget ?? 0,
    budget_type: row.budget_type,
    notes: row.notes,
  }
  campaignDateRange.value = row.start_date && row.end_date ? [row.start_date, row.end_date] as [string, string] : null
  showCampaignForm.value = true
}

async function deleteCampaign(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这个投放计划吗？')
    await api.campaigns.delete(id)
    ElMessage.success('已删除')
    await loadCampaigns()
  } catch { /* cancelled */ }
}

// ── Product tab ──────────────────────────────

const showProductForm = ref(false)
const editingProduct = ref<api.Product | null>(null)
const productForm = ref({
  name: '',
  category: '',
  selling_points_text: '',
  ingredients_text: '',
  target_audience: '',
  brand: '俏小喵',
  notes: '',
})
const productsList = ref<api.Product[]>([])
const productsLoading = ref(false)
const productsError = ref('')

async function loadProducts() {
  productsLoading.value = true
  productsError.value = ''
  try {
    productsList.value = await api.products.list()
  } catch (e: unknown) {
    showLoadError(productsError, '产品列表加载失败', e)
  }
  finally { productsLoading.value = false }
}

function resetProductForm() {
  productForm.value = { name: '', category: '', selling_points_text: '', ingredients_text: '', target_audience: '', brand: '俏小喵', notes: '' }
}

async function submitProduct() {
  if (!productForm.value.name.trim()) {
    ElMessage.warning('请输入产品名称')
    return
  }
  try {
    const data: Partial<api.Product> = {
      name: productForm.value.name.trim(),
      category: productForm.value.category.trim(),
      selling_points: productForm.value.selling_points_text.split('\n').filter(Boolean),
      ingredients: productForm.value.ingredients_text.split('\n').filter(Boolean),
      target_audience: productForm.value.target_audience.trim(),
      brand: productForm.value.brand.trim() || '俏小喵',
      notes: productForm.value.notes.trim(),
    }
    if (editingProduct.value) {
      await api.products.update(editingProduct.value.id, data)
      ElMessage.success('产品已更新')
    } else {
      await api.products.create(data)
      ElMessage.success('产品已添加')
    }
    showProductForm.value = false
    editingProduct.value = null
    resetProductForm()
    await loadProducts()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  }
}

function editProduct(row: api.Product) {
  editingProduct.value = row
  productForm.value = {
    name: row.name,
    category: row.category,
    selling_points_text: row.selling_points?.join('\n') || '',
    ingredients_text: row.ingredients?.join('\n') || '',
    target_audience: row.target_audience,
    brand: row.brand,
    notes: row.notes,
  }
  showProductForm.value = true
}

async function deleteProduct(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这个产品吗？')
    await api.products.delete(id)
    ElMessage.success('已删除')
    await loadProducts()
  } catch { /* cancelled */ }
}

// ── Validate tab ──────────────────────────────

const validateInput = ref('')
const validateLoading = ref(false)
const validateResult = ref<api.ValidationResult | null>(null)

async function doValidate() {
  if (!validateInput.value.trim()) {
    ElMessage.warning('请输入需要校验的内容')
    return
  }
  validateLoading.value = true
  try {
    validateResult.value = await api.validation.validate(validateInput.value.trim())
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '校验失败')
  } finally {
    validateLoading.value = false
  }
}

// ── Prompt tab ───────────────────────────────

const showPromptForm = ref(false)
const editingPrompt = ref<api.Prompt | null>(null)
const promptForm = ref({
  key: '',
  name: '',
  content: '',
  description: '',
  category: 'custom',
  channel: '',
})
const promptsList = ref<api.Prompt[]>([])
const promptsLoading = ref(false)
const promptsError = ref('')

async function loadPrompts() {
  promptsLoading.value = true
  promptsError.value = ''
  try {
    promptsList.value = await api.prompts.list()
  } catch (e: unknown) {
    showLoadError(promptsError, '提示词列表加载失败', e)
  }
  finally { promptsLoading.value = false }
}

function resetPromptForm() {
  promptForm.value = { key: '', name: '', content: '', description: '', category: 'custom', channel: '' }
}

async function submitPrompt() {
  if (!promptForm.value.key.trim() || !promptForm.value.content.trim()) {
    ElMessage.warning('Key 和内容不能为空')
    return
  }
  try {
    await api.prompts.save({ ...promptForm.value })
    ElMessage.success('提示词已保存')
    showPromptForm.value = false
    editingPrompt.value = null
    resetPromptForm()
    await loadPrompts()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  }
}

function editPrompt(row: api.Prompt) {
  editingPrompt.value = row
  promptForm.value = {
    key: row.key,
    name: row.name,
    content: row.content,
    description: row.description,
    category: row.category,
    channel: row.channel,
  }
  showPromptForm.value = true
}

async function deletePrompt(id: number) {
  try {
    await ElMessageBox.confirm('确定删除这个提示词吗？')
    await api.prompts.delete(id)
    ElMessage.success('已删除')
    await loadPrompts()
  } catch { /* cancelled */ }
}

// ── Init ─────────────────────────────────────

onMounted(() => {
  loadScripts()
  loadAdCopies()
  loadCampaigns()
  loadProducts()
  loadPrompts()
})
</script>

<style scoped>
.douyin-app {
  height: 100%;
  display: flex;
  flex-direction: column;
  padding: 16px;
  box-sizing: border-box;
  overflow: auto;
  background: #fff;
}
.dy-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.dy-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #1f2937;
}
.dy-tabs {
  flex: 1;
}
.tab-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 8px;
  flex-wrap: wrap;
}
.toolbar-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.result-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin-bottom: 16px;
  overflow: hidden;
}
.result-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: #f5f7fa;
  border-bottom: 1px solid #e4e7ed;
}
.result-label {
  font-weight: 600;
  font-size: 13px;
  display: flex;
  align-items: center;
}
.result-actions {
  display: flex;
  gap: 6px;
}
.result-content {
  padding: 12px;
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
  background: #fafafa;
}
.list-section {
  margin-top: 8px;
}
.list-section h3 {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.list-error {
  margin-bottom: 8px;
}
.form-card {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  padding: 16px;
  margin-bottom: 16px;
  background: #fafafa;
}
.form-card h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 600;
}
.dialog-content {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.6;
  max-height: 400px;
  overflow-y: auto;
}
</style>
