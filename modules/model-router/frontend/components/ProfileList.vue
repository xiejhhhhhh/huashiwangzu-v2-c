<template>
  <div class="profile-list">
    <div class="profile-list__toolbar">
      <el-button type="primary" size="small" @click="openCreateDialog">+ 新增档案</el-button>
      <el-button size="small" :loading="loading" @click="load">刷新</el-button>
    </div>

    <el-collapse v-model="activeGroups" v-loading="loading">
      <el-collapse-item v-for="(list, modelType) in grouped" :key="modelType" :name="modelType">
        <template #title>
          <span class="profile-list__group-title">{{ modelType }}</span>
          <span class="profile-list__group-count">{{ list.length }} 个</span>
        </template>

        <el-table :data="list" size="small" stripe style="width: 100%">
          <el-table-column prop="profile_key" label="档案 key" min-width="160" show-overflow-tooltip />
          <el-table-column prop="provider" label="提供商" width="120" />
          <el-table-column prop="model" label="模型" min-width="160" show-overflow-tooltip />
          <el-table-column prop="temperature" label="温度" width="80" />
          <el-table-column prop="max_tokens" label="最大输出" width="100" />
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag v-if="row.deprecated" type="warning" size="small">已弃用</el-tag>
              <el-tag v-else type="success" size="small">启用中</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" @click="openEditDialog(row)">编辑</el-button>
              <el-button link size="small" type="danger" @click="handleDelete(row.profile_key)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editingKey ? '编辑档案' : '新增档案'" width="480px">
      <el-form :model="form" label-width="100px" size="small">
        <el-form-item label="档案 key">
          <el-input v-model="form.profile_key" :disabled="!!editingKey" placeholder="如 llm-main" />
        </el-form-item>
        <el-form-item label="模型类型">
          <el-input v-model="form.model_type" placeholder="如 llm / vision / embedding" />
        </el-form-item>
        <el-form-item label="提供商">
          <el-input v-model="form.provider" placeholder="提供商 key" />
        </el-form-item>
        <el-form-item label="模型">
          <el-input v-model="form.model" placeholder="模型名称" />
        </el-form-item>
        <el-form-item label="温度">
          <el-input-number v-model="form.temperature" :min="0" :max="2" :step="0.1" />
        </el-form-item>
        <el-form-item label="最大输出">
          <el-input-number v-model="form.max_tokens" :min="1" :step="256" />
        </el-form-item>
        <el-form-item label="已弃用">
          <el-switch v-model="form.deprecated" />
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
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { ModelProfileItem } from '../api'
import * as api from '../api'

const grouped = ref<Record<string, ModelProfileItem[]>>({})
const activeGroups = ref<string[]>([])
const loading = ref(false)

const dialogVisible = ref(false)
const editingKey = ref('')
const saving = ref(false)
const form = reactive<ModelProfileItem>({
  profile_key: '',
  model_type: '',
  provider: '',
  model: '',
  temperature: 0.7,
  max_tokens: 4096,
  deprecated: false,
})

const allTypes = computed(() => Object.keys(grouped.value))

function resetForm() {
  form.profile_key = ''
  form.model_type = ''
  form.provider = ''
  form.model = ''
  form.temperature = 0.7
  form.max_tokens = 4096
  form.deprecated = false
}

async function load() {
  loading.value = true
  try {
    const r = await api.profiles.list()
    grouped.value = r.profiles
    if (activeGroups.value.length === 0) {
      activeGroups.value = [...allTypes.value]
    }
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '模型档案加载失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  editingKey.value = ''
  resetForm()
  dialogVisible.value = true
}

function openEditDialog(row: ModelProfileItem) {
  editingKey.value = row.profile_key
  form.profile_key = row.profile_key
  form.model_type = row.model_type
  form.provider = row.provider
  form.model = row.model
  form.temperature = row.temperature ?? 0.7
  form.max_tokens = row.max_tokens ?? 4096
  form.deprecated = !!row.deprecated
  dialogVisible.value = true
}

async function handleSubmit() {
  if (!form.profile_key.trim()) {
    ElMessage.warning('请输入档案 key')
    return
  }
  saving.value = true
  try {
    if (editingKey.value) {
      await api.profiles.update(editingKey.value, { ...form })
      ElMessage.success('档案已更新')
    } else {
      await api.profiles.create({ ...form })
      ElMessage.success('档案已创建')
    }
    dialogVisible.value = false
    await load()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete(key: string) {
  try {
    await ElMessageBox.confirm(`确定删除档案 "${key}" 吗？`, '提示', { type: 'warning' })
    await api.profiles.delete(key)
    ElMessage.success('已删除')
    await load()
  } catch { /* 用户取消 */ }
}

onMounted(load)

defineExpose({ load })
</script>

<style scoped>
.profile-list__toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}
.profile-list__group-title {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
}
.profile-list__group-count {
  margin-left: 8px;
  font-size: 12px;
  color: #9ca3af;
}
</style>
