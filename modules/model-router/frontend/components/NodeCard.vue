<template>
  <el-card class="node-card" shadow="hover">
    <template #header>
      <div class="node-card__header">
        <span class="node-card__dot" :class="`is-${node.health}`" :title="healthLabel"></span>
        <span class="node-card__name">{{ node.name }}</span>
        <span class="node-card__id">{{ node.id }}</span>
      </div>
    </template>

    <div class="node-card__row">
      <label class="node-card__label">当前档案</label>
      <el-select v-model="form.profile_key" size="small" class="node-card__select" @change="onProfileChange">
        <el-option v-for="p in node.candidates" :key="p" :label="p" :value="p" />
      </el-select>
    </div>

    <div class="node-card__row">
      <label class="node-card__label">模型</label>
      <el-tag size="small" type="info">{{ node.profile_detail?.model || '-' }}</el-tag>
      <label class="node-card__label node-card__label--gap">提供商</label>
      <el-tag size="small">{{ node.provider || '-' }}</el-tag>
    </div>

    <div class="node-card__row">
      <label class="node-card__label">温度</label>
      <el-slider
        v-model="form.temperature"
        :min="0"
        :max="2"
        :step="0.1"
        show-input
        size="small"
        class="node-card__slider"
      />
    </div>

    <div class="node-card__row">
      <label class="node-card__label">最大输出</label>
      <el-input-number v-model="form.max_tokens" :min="1" :step="256" size="small" controls-position="right" />
      <label class="node-card__label node-card__label--gap">上下文预算</label>
      <el-input-number v-model="form.context_budget" :min="0" :step="10000" size="small" controls-position="right" />
    </div>

    <div class="node-card__row node-card__row--fallback">
      <label class="node-card__label">降级链</label>
      <div class="node-card__fallback-list">
        <el-tag
          v-for="(fb, idx) in form.fallback_chain"
          :key="`${fb}-${idx}`"
          closable
          size="small"
          class="node-card__fallback-tag"
          @close="removeFallback(idx)"
        >
          {{ fb }}
        </el-tag>

        <el-select
          v-if="addingFallback"
          v-model="pendingFallback"
          size="small"
          class="node-card__fallback-select"
          placeholder="选择降级档案"
          @change="confirmAddFallback"
          @visible-change="onFallbackSelectVisibleChange"
        >
          <el-option v-for="p in node.candidates" :key="p" :label="p" :value="p" />
        </el-select>
        <el-button v-else size="small" text @click="addingFallback = true">+ 添加</el-button>
      </div>
    </div>

    <div class="node-card__footer">
      <span class="node-card__group-tag">{{ node.group }}</span>
      <el-button type="primary" size="small" :loading="saving" @click="handleSave">保存</el-button>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { RouterNode, NodeUpdatePayload } from '../api'
import * as api from '../api'

const props = defineProps<{ node: RouterNode }>()
const emit = defineEmits<{ (e: 'updated', node: RouterNode): void }>()

const healthLabelMap: Record<string, string> = { ok: '健康', degraded: '降级', down: '不可用' }
const healthLabel = healthLabelMap[props.node.health] ?? props.node.health

const form = reactive({
  profile_key: props.node.current_profile,
  temperature: props.node.profile_detail?.temperature ?? null,
  max_tokens: props.node.profile_detail?.max_tokens ?? null,
  context_budget: props.node.profile_detail?.context_budget ?? null,
  fallback_chain: [...(props.node.fallback_chain || [])],
})

const saving = ref(false)
const addingFallback = ref(false)
const pendingFallback = ref('')

// 节点数据外部刷新时同步表单
watch(
  () => props.node,
  (n) => {
    form.profile_key = n.current_profile
    form.temperature = n.profile_detail?.temperature ?? null
    form.max_tokens = n.profile_detail?.max_tokens ?? null
    form.context_budget = n.profile_detail?.context_budget ?? null
    form.fallback_chain = [...(n.fallback_chain || [])]
  },
)

function onProfileChange() {
  // 切换档案后温度/最大输出仍沿用当前表单值，由使用者手动调整
}

function removeFallback(idx: number) {
  form.fallback_chain.splice(idx, 1)
}

function confirmAddFallback(value: string) {
  if (value && !form.fallback_chain.includes(value)) {
    form.fallback_chain.push(value)
  }
  pendingFallback.value = ''
  addingFallback.value = false
}

function onFallbackSelectVisibleChange(visible: boolean) {
  if (!visible && !pendingFallback.value) {
    addingFallback.value = false
  }
}

async function handleSave() {
  saving.value = true
  try {
    const payload: NodeUpdatePayload = {
      profile_key: form.profile_key,
      temperature: form.temperature ?? undefined,
      max_tokens: form.max_tokens ?? undefined,
      context_budget: form.context_budget ?? undefined,
      fallback_chain: form.fallback_chain,
    }
    const updated = await api.nodes.update(props.node.id, payload)
    ElMessage.success(`${props.node.name} 保存成功`)
    emit('updated', updated)
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '保存失败')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.node-card {
  border-radius: 8px;
}
.node-card :deep(.el-card__header) {
  padding: 10px 16px;
}
.node-card :deep(.el-card__body) {
  padding: 14px 16px;
}
.node-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.node-card__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
  background: #c0c4cc;
}
.node-card__dot.is-ok { background: #67c23a; }
.node-card__dot.is-degraded { background: #e6a23c; }
.node-card__dot.is-down { background: #f56c6c; }
.node-card__name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}
.node-card__id {
  font-size: 11px;
  color: #9ca3af;
  margin-left: auto;
}
.node-card__row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.node-card__row--fallback {
  align-items: flex-start;
}
.node-card__label {
  font-size: 12px;
  color: #6b7280;
  flex-shrink: 0;
  min-width: 56px;
}
.node-card__label--gap {
  margin-left: 8px;
}
.node-card__select {
  flex: 1;
  min-width: 140px;
}
.node-card__slider {
  flex: 1;
  min-width: 160px;
}
.node-card__fallback-list {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
}
.node-card__fallback-tag {
  margin: 0;
}
.node-card__fallback-select {
  width: 160px;
}
.node-card__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  border-top: 1px solid #f0f2f5;
}
.node-card__group-tag {
  font-size: 11px;
  color: #9ca3af;
}
</style>
