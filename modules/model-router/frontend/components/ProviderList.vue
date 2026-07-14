<template>
  <div class="provider-list">
    <div class="provider-list__toolbar">
      <el-button type="primary" size="small" @click="openCreateDialog">+ 新增提供商</el-button>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-table :data="items" v-loading="loading" size="small" stripe style="width: 100%">
      <el-table-column prop="key" label="名称" min-width="140" show-overflow-tooltip />
      <el-table-column prop="type" label="类型" width="110" />
      <el-table-column prop="api_url" label="API 地址" min-width="220" show-overflow-tooltip />
      <el-table-column prop="api_key_env" label="密钥环境变量" width="160" show-overflow-tooltip />
      <el-table-column label="测试状态" width="160">
        <template #default="{ row }">
          <span v-if="testResults[row.key] === undefined" class="provider-list__test-idle">未测试</span>
          <el-tag v-else-if="testResults[row.key]?.success" type="success" size="small">
            正常（{{ testResults[row.key]?.latency_ms }}ms）
          </el-tag>
          <el-tag v-else type="danger" size="small" :title="testResults[row.key]?.error">
            失败：{{ testResults[row.key]?.error }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <el-button link size="small" :loading="testingKey === row.key" @click="handleTest(row.key)">测试</el-button>
          <el-button link size="small" @click="openEditDialog(row)">编辑</el-button>
          <el-button link size="small" type="danger" @click="handleDelete(row.key)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingKey ? '编辑提供商' : '新增提供商'" width="480px">
      <el-form :model="form" label-width="110px" size="small">
        <el-form-item label="名称 key">
          <el-input v-model="form.key" :disabled="!!editingKey" placeholder="如 openai / mimo" />
        </el-form-item>
        <el-form-item label="类型">
          <el-input v-model="form.type" placeholder="如 openai_compatible" />
        </el-form-item>
        <el-form-item label="API 地址">
          <el-input v-model="form.api_url" placeholder="https://..." />
        </el-form-item>
        <el-form-item label="密钥环境变量">
          <el-input v-model="form.api_key_env" placeholder="如 OPENAI_API_KEY" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button size="small" @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" size="small" :loading="saving" @click="handleSubmit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ProviderItem, ProviderTestResult } from '../api'
import * as api from '../api'

const items = ref<ProviderItem[]>([])
const loading = ref(false)
const testingKey = ref('')
const testResults = reactive<Record<string, ProviderTestResult | undefined>>({})

const dialogVisible = ref(false)
const editingKey = ref('')
const saving = ref(false)
const form = reactive<ProviderItem>({ key: '', type: '', api_url: '', api_key_env: '', description: '' })

function resetForm() {
  form.key = ''
  form.type = ''
  form.api_url = ''
  form.api_key_env = ''
  form.description = ''
}

async function load() {
  loading.value = true
  try {
    const r = await api.providers.list()
    items.value = r.providers
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '提供商列表加载失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingKey.value = ''
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row: ProviderItem) {
  editingKey.value = row.key
  form.key = row.key
  form.type = row.type
  form.api_url = row.api_url
  form.api_key_env = row.api_key_env
  form.description = row.description
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!form.key.trim()) {
    ElMessage.warning('请输入名称 key')
    return
  }
  saving.value = true
  try {
    if (editingKey.value) {
      await api.providers.update(editingKey.value, { ...form })
      ElMessage.success('提供商已更新')
    } else {
      await api.providers.create({ ...form })
      ElMessage.success('提供商已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTest(key: string) {
  testingKey.value = key
  try {
    const result = await api.providers.test(key)
    testResults[key] = result
    if (result.success) {
      ElMessage.success(`${key} 连接正常`)
    } else {
      ElMessage.error(`${key} 连接失败：${result.error ?? '未知错误'}`)
    }
  } catch (e: unknown) {
    const message = (e as Error).message || '测试失败'
    testResults[key] = { success: false, error: message }
    ElMessage.error(message)
  } finally {
    testingKey.value = ''
  }
}

async function handleDelete(key: string) {
  try {
    await ElMessageBox.confirm(`确定删除提供商 "${key}" 吗？`, '提示', { type: 'warning' })
    await api.providers.delete(key)
    ElMessage.success('已删除')
    await load()
  } catch { /* 用户取消 */ }
}

onMounted(load)

defineExpose({ load })
</script>

<style scoped>
.provider-list__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.provider-list__test-idle {
  font-size: 12px;
  color: #9ca3af;
}
</style>
