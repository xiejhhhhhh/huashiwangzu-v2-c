<template>
  <div class="agent-config-panel">
    <header class="acp-header">
      <h2 class="acp-title">Agent 配置管理</h2>
      <span class="acp-subtitle">仅管理员 · 模块表 agent_configs</span>
    </header>

    <div v-if="loading" class="acp-loading">加载中...</div>
    <div v-else-if="error" class="acp-error">{{ error }}</div>
    <template v-else>
      <!-- 配置列表 -->
      <section class="acp-section">
        <div class="acp-toolbar">
          <h3 class="acp-section-title">所有 Agent 配置</h3>
          <button class="acp-btn acp-btn-primary" @click="showCreateForm = true" v-if="!showCreateForm">+ 新建配置</button>
        </div>

        <!-- 新建表单 -->
        <div v-if="showCreateForm" class="acp-form-card">
          <h4 class="acp-form-title">新建 Agent 配置</h4>
          <div class="acp-form-grid">
            <label>agent_code <input v-model="form.agent_code" placeholder="唯一标识" class="acp-input" /></label>
            <label>名称 <input v-model="form.agent_name" placeholder="显示名称" class="acp-input" /></label>
            <label>模型档 <input v-model="form.model" placeholder="models.json profile key" class="acp-input" /></label>
            <label>provider <input v-model="form.provider" placeholder="models.json provider name" class="acp-input" /></label>
            <label>用途 <input v-model="form.purpose" placeholder="用途简述" class="acp-input" /></label>
            <label>对外授权策略
              <select v-model="form.sensitive_action_policy" class="acp-input">
                <option value="confirm">confirm（对外发送前确认）</option>
                <option value="allow">allow（直接执行）</option>
                <option value="block">block（禁止）</option>
              </select>
            </label>
          </div>
          <label class="acp-full-label">系统提示词
            <textarea v-model="form.system_prompt" rows="3" class="acp-textarea"></textarea>
          </label>
          <div class="acp-form-actions">
            <button class="acp-btn acp-btn-primary" @click="createConfig" :disabled="saving">创建</button>
            <button class="acp-btn" @click="showCreateForm = false; resetForm()">取消</button>
          </div>
        </div>

        <!-- 配置表格 -->
        <table class="acp-table" v-if="configs.length">
          <thead>
            <tr>
              <th>agent_code</th>
              <th>名称</th>
              <th>模型</th>
              <th>启用</th>
              <th>对外授权</th>
              <th>今日调用</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="c in configs" :key="c.agent_code">
              <td class="acp-cell-code">{{ c.agent_code }}</td>
              <td>{{ c.agent_name }}</td>
              <td>{{ c.model || '-' }}</td>
              <td>
                <span :class="c.enabled ? 'acp-badge-green' : 'acp-badge-gray'">
                  {{ c.enabled ? '启用' : '停用' }}
                </span>
              </td>
              <td>
                <span :class="policyBadgeClass(c.sensitive_action_policy)">
                  {{ policyLabel(c.sensitive_action_policy) }}
                </span>
              </td>
              <td>{{ todayCalls[c.agent_code] ?? '-' }}</td>
              <td>
                <button class="acp-btn-sm" @click="editConfig(c)">编辑</button>
                <button class="acp-btn-sm acp-btn-danger" @click="deleteConfig(c)" :disabled="deleting === c.agent_code">删除</button>
              </td>
            </tr>
          </tbody>
        </table>
        <div v-else class="acp-empty">暂无配置，请新建</div>
      </section>

      <!-- 编辑面板 -->
      <div v-if="editing" class="acp-form-card">
        <h4 class="acp-form-title">编辑 {{ editing.agent_code }}</h4>
        <div class="acp-form-grid">
          <label>启用
            <select v-model="editForm.enabled" class="acp-input">
              <option :value="true">启用</option>
              <option :value="false">停用</option>
            </select>
          </label>
          <label>模型档 <input v-model="editForm.model" class="acp-input" /></label>
          <label>provider <input v-model="editForm.provider" class="acp-input" /></label>
          <label>temperature <input v-model.number="editForm.temperature" type="number" step="0.1" class="acp-input" /></label>
          <label>top_p <input v-model.number="editForm.top_p" type="number" step="0.1" class="acp-input" /></label>
          <label>max_tokens <input v-model.number="editForm.max_tokens" type="number" class="acp-input" /></label>
          <label>timeout_ms <input v-model.number="editForm.timeout_ms" type="number" class="acp-input" /></label>
          <label>fallback_model <input v-model="editForm.fallback_model" class="acp-input" /></label>
          <label>fallback_enabled
            <select v-model="editForm.fallback_enabled" class="acp-input">
              <option :value="true">是</option>
              <option :value="false">否</option>
            </select>
          </label>
          <label>max_concurrency <input v-model.number="editForm.max_concurrency" type="number" class="acp-input" /></label>
          <label>cooldown_seconds <input v-model.number="editForm.cooldown_seconds" type="number" class="acp-input" /></label>
          <label>retry_count <input v-model.number="editForm.retry_count" type="number" class="acp-input" /></label>
          <label>daily_call_limit <input v-model.number="editForm.daily_call_limit" type="number" class="acp-input" /></label>
          <label>daily_budget (¥) <input v-model.number="editForm.daily_budget" type="number" step="0.01" class="acp-input" /></label>
          <label>monthly_budget (¥) <input v-model.number="editForm.monthly_budget" type="number" step="0.01" class="acp-input" /></label>
          <label>response_format
            <select v-model="editForm.response_format" class="acp-input">
              <option value="text">text</option>
              <option value="json_object">json_object</option>
            </select>
          </label>
          <label>对外授权策略
            <select v-model="editForm.sensitive_action_policy" class="acp-input">
              <option value="allow">allow（直接执行）</option>
              <option value="confirm">confirm（对外发送前确认）</option>
              <option value="block">block（禁止）</option>
            </select>
          </label>
          <label>日志提示词
            <select v-model="editForm.log_prompt_enabled" class="acp-input">
              <option :value="true">记录</option>
              <option :value="false">不记录</option>
            </select>
          </label>
          <label>日志响应
            <select v-model="editForm.log_response_enabled" class="acp-input">
              <option :value="true">记录</option>
              <option :value="false">不记录</option>
            </select>
          </label>
        </div>
        <label class="acp-full-label">系统提示词
          <textarea v-model="editForm.system_prompt" rows="4" class="acp-textarea"></textarea>
        </label>
        <div class="acp-form-actions">
          <button class="acp-btn acp-btn-primary" @click="saveEdit" :disabled="saving">保存</button>
          <button class="acp-btn" @click="editing = null">取消</button>
        </div>
      </div>

      <!-- 今日用量摘要 -->
      <section class="acp-section" v-if="costData">
        <h3 class="acp-section-title">今日模型用量</h3>
        <div class="acp-card-grid">
          <div class="acp-card">
            <div class="acp-card-value">{{ costData.today_total ?? '-' }}</div>
            <div class="acp-card-label">总花费 (¥)</div>
          </div>
        </div>
      </section>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { apiGet, apiPost, apiPut, apiDelete } from '../api'

interface AgentConfigItem {
  id: number
  agent_code: string
  agent_name: string
  provider: string
  model: string
  system_prompt: string
  purpose: string
  enabled: boolean
  temperature: number | null
  top_p: number | null
  max_tokens: number | null
  timeout_ms: number | null
  fallback_model: string | null
  fallback_enabled: boolean
  max_concurrency: number | null
  cooldown_seconds: number | null
  retry_count: number
  daily_call_limit: number | null
  daily_budget: number | null
  monthly_budget: number | null
  response_format: string
  log_prompt_enabled: boolean
  log_response_enabled: boolean
  sensitive_action_policy: string
  updated_by: number | null
  created_at: string | null
  updated_at: string | null
}

const loading = ref(true)
const error = ref('')
const configs = ref<AgentConfigItem[]>([])
const saving = ref(false)
const showCreateForm = ref(false)
const editing = ref<AgentConfigItem | null>(null)
const deleting = ref<string | null>(null)
const todayCalls = ref<Record<string, number>>({})
interface CostData {
  today_total?: number
  [key: string]: unknown
}

const costData = ref<CostData | null>(null)

const form = ref({
  agent_code: '', agent_name: '', provider: '', model: '',
  system_prompt: '', purpose: '', sensitive_action_policy: 'confirm',
})
interface EditForm {
  enabled: boolean
  model: string
  provider: string
  temperature: number | null
  top_p: number | null
  max_tokens: number | null
  timeout_ms: number | null
  fallback_model: string | null
  fallback_enabled: boolean
  max_concurrency: number | null
  cooldown_seconds: number | null
  retry_count: number
  daily_call_limit: number | null
  daily_budget: number | null
  monthly_budget: number | null
  response_format: string
  log_prompt_enabled: boolean
  log_response_enabled: boolean
  sensitive_action_policy: string
  system_prompt: string
  [key: string]: unknown
}

const editForm = ref<EditForm>({} as EditForm)

function resetForm() {
  form.value = { agent_code: '', agent_name: '', provider: '', model: '', system_prompt: '', purpose: '', sensitive_action_policy: 'confirm' }
}

function policyLabel(p: string): string {
  if (p === 'allow') return '允许'
  if (p === 'confirm') return '对外确认'
  return '禁止'
}

function policyBadgeClass(p: string): string {
  if (p === 'allow') return 'acp-badge-green'
  if (p === 'confirm') return 'acp-badge-yellow'
  return 'acp-badge-red'
}

async function httpJson<T>(path: string, method: string = 'GET', body?: unknown): Promise<T> {
  if (method === 'GET') return apiGet<T>(path)
  if (method === 'POST' && body) return apiPost<T>(path, body as Record<string, unknown>)
  if (method === 'PUT') return apiPut<T>(path, body as Record<string, unknown>)
  if (method === 'DELETE') return apiDelete<T>(path)
  throw new Error(`Unsupported method: ${method}`)
}

async function loadConfigs() {
  loading.value = true
  error.value = ''
  try {
    configs.value = await httpJson<AgentConfigItem[]>('/agent/configs')
    try {
      interface AdminOverview { cost?: CostData }
      const overview = await httpJson<AdminOverview>('/agent/admin/overview')
      if (overview.cost) {
        costData.value = overview.cost
      }
    } catch { /* ignore */ }
  } catch (e: unknown) {
    error.value = String((e as Error).message || e)
  } finally {
    loading.value = false
  }
}

async function createConfig() {
  if (!form.value.agent_code.trim()) {
    alert('agent_code 不能为空')
    return
  }
  saving.value = true
  try {
    const newConfig = await httpJson<AgentConfigItem>('/agent/configs', 'POST', form.value)
    configs.value.push(newConfig)
    showCreateForm.value = false
    resetForm()
    alert('创建成功')
  } catch (e: unknown) {
    alert('创建失败: ' + String((e as Error).message || e))
  } finally {
    saving.value = false
  }
}

function editConfig(c: AgentConfigItem) {
  editing.value = c
  editForm.value = {
    enabled: c.enabled,
    model: c.model,
    provider: c.provider,
    temperature: c.temperature,
    top_p: c.top_p,
    max_tokens: c.max_tokens,
    timeout_ms: c.timeout_ms,
    fallback_model: c.fallback_model,
    fallback_enabled: c.fallback_enabled,
    max_concurrency: c.max_concurrency,
    cooldown_seconds: c.cooldown_seconds,
    retry_count: c.retry_count,
    daily_call_limit: c.daily_call_limit,
    daily_budget: c.daily_budget,
    monthly_budget: c.monthly_budget,
    response_format: c.response_format,
    log_prompt_enabled: c.log_prompt_enabled,
    log_response_enabled: c.log_response_enabled,
    sensitive_action_policy: c.sensitive_action_policy,
    system_prompt: c.system_prompt,
  }
}

async function saveEdit() {
  if (!editing.value) return
  saving.value = true
  try {
    const updated = await httpJson<AgentConfigItem>(`/agent/configs/${editing.value.agent_code}`, 'PUT', editForm.value)
    const idx = configs.value.findIndex(c => c.agent_code === editing.value!.agent_code)
    if (idx >= 0) configs.value[idx] = updated
    editing.value = null
    alert('保存成功')
  } catch (e: unknown) {
    alert('保存失败: ' + String((e as Error).message || e))
  } finally {
    saving.value = false
  }
}

async function deleteConfig(c: AgentConfigItem) {
  if (!confirm(`确定删除 "${c.agent_code}" 的配置？`)) { return }
  deleting.value = c.agent_code
  try {
    await httpJson(`/agent/configs/${c.agent_code}`, 'DELETE')
    configs.value = configs.value.filter(x => x.agent_code !== c.agent_code)
    alert('已删除')
  } catch (e: unknown) {
    alert('删除失败: ' + String((e as Error).message || e))
  } finally {
    deleting.value = null
  }
}

onMounted(loadConfigs)
</script>

<style scoped>
.agent-config-panel {
  --acp-primary: #2395bc;
  --acp-primary-light: #e8f6fb;
  --acp-bg: #f7f9fa;
  --acp-card-bg: #ffffff;
  --acp-text: #1a1a1a;
  --acp-text-secondary: #5e5e5e;
  --acp-border: #e2e6e9;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif;
  font-size: 13px;
  color: var(--acp-text);
  background: var(--acp-bg);
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px;
}
.acp-header { margin-bottom: 20px; display: flex; align-items: baseline; gap: 12px; }
.acp-title { font-size: 18px; font-weight: 600; margin: 0; color: var(--acp-text); }
.acp-subtitle { font-size: 12px; color: var(--acp-text-secondary); }
.acp-loading, .acp-error { padding: 40px; text-align: center; color: var(--acp-text-secondary); }
.acp-error { color: #f56c6c; }
.acp-section { margin-bottom: 24px; }
.acp-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.acp-section-title { font-size: 14px; font-weight: 600; margin: 0; }

/* Table */
.acp-table { width: 100%; border-collapse: collapse; font-size: 12px; background: var(--acp-card-bg); border-radius: 6px; overflow: hidden; }
.acp-table th { background: var(--acp-primary-light); padding: 10px 12px; text-align: left; font-weight: 600; color: var(--acp-text); border-bottom: 1px solid var(--acp-border); }
.acp-table td { padding: 8px 12px; border-bottom: 1px solid var(--acp-border); }
.acp-table tr:last-child td { border-bottom: none; }
.acp-table tr:hover td { background: #f0f6f9; }
.acp-cell-code { font-family: 'SF Mono', 'Monaco', 'Menlo', monospace; font-weight: 600; color: var(--acp-primary); }
.acp-empty { padding: 40px; text-align: center; color: var(--acp-text-secondary); }

/* Badges */
.acp-badge-green { background: #e1f3e1; color: #1f7a1f; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.acp-badge-gray { background: #eee; color: #666; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.acp-badge-yellow { background: #fff3cd; color: #856404; padding: 2px 8px; border-radius: 3px; font-size: 11px; }
.acp-badge-red { background: #f8d7da; color: #721c24; padding: 2px 8px; border-radius: 3px; font-size: 11px; }

/* Buttons */
.acp-btn {
  height: 32px; padding: 0 16px; border: 1px solid var(--acp-border);
  background: var(--acp-card-bg); color: var(--acp-text);
  border-radius: 4px; font-size: 13px; cursor: pointer;
  transition: all 0.15s;
}
.acp-btn:hover { border-color: var(--acp-primary); color: var(--acp-primary); }
.acp-btn-primary { background: var(--acp-primary); color: #fff; border-color: var(--acp-primary); }
.acp-btn-primary:hover { background: #1a8aaa; color: #fff; }
.acp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.acp-btn-sm {
  height: 26px; padding: 0 10px; border: 1px solid var(--acp-border);
  background: var(--acp-card-bg); color: var(--acp-text);
  border-radius: 3px; font-size: 11px; cursor: pointer; margin-right: 4px;
  transition: all 0.15s;
}
.acp-btn-sm:hover { border-color: var(--acp-primary); color: var(--acp-primary); }
.acp-btn-danger { color: #f56c6c; }
.acp-btn-danger:hover { border-color: #f56c6c; color: #f56c6c; background: #fef0f0; }

/* Form */
.acp-form-card {
  background: var(--acp-card-bg); border: 1px solid var(--acp-border);
  border-radius: 6px; padding: 16px 20px; margin-bottom: 16px;
}
.acp-form-title { font-size: 14px; font-weight: 600; margin: 0 0 12px; }
.acp-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.acp-form-grid label { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--acp-text-secondary); }
.acp-full-label { display: flex; flex-direction: column; gap: 3px; font-size: 11px; color: var(--acp-text-secondary); margin-top: 10px; }
.acp-input {
  height: 30px; padding: 0 8px; border: 1px solid var(--acp-border);
  border-radius: 4px; font-size: 13px; outline: none;
  transition: border-color 0.15s;
}
.acp-input:focus { border-color: var(--acp-primary); }
.acp-textarea {
  padding: 8px; border: 1px solid var(--acp-border);
  border-radius: 4px; font-size: 13px; outline: none; resize: vertical;
  font-family: inherit; transition: border-color 0.15s;
}
.acp-textarea:focus { border-color: var(--acp-primary); }
.acp-form-actions { display: flex; gap: 8px; margin-top: 12px; justify-content: flex-end; }
select.acp-input { background: var(--acp-card-bg); }

/* Cards */
.acp-card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 10px; margin-top: 8px; }
.acp-card { background: var(--acp-card-bg); border: 1px solid var(--acp-border); border-radius: 6px; padding: 12px 14px; }
.acp-card-value { font-size: 20px; font-weight: 700; color: var(--acp-primary); line-height: 1.2; }
.acp-card-label { font-size: 11px; color: var(--acp-text-secondary); margin-top: 4px; }
</style>
