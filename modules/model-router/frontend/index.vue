<template>
  <div class="model-router-page">
    <div class="model-router-page__topbar">
      <div class="model-router-page__title">
        <span class="model-router-page__dot" :class="`is-${overallHealth}`" :title="overallHealthLabel"></span>
        <span class="model-router-page__title-text">模型路由管理器</span>
      </div>
      <div class="model-router-page__actions">
        <el-button size="small" :loading="testingAll" @click="handleTestAll">测试全部</el-button>
        <el-button type="primary" size="small" :loading="reloading" @click="handleReload">重载配置</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" class="model-router-page__tabs">
      <el-tab-pane label="调用节点" name="nodes">
        <div v-loading="nodesLoading" class="model-router-page__nodes">
          <el-collapse v-model="activeNodeGroups">
            <el-collapse-item v-for="group in nodeGroups" :key="group.key" :name="group.key">
              <template #title>
                <span class="model-router-page__group-title">{{ group.label }}</span>
                <span class="model-router-page__group-count">{{ group.nodes.length }} 个节点</span>
              </template>
              <el-divider content-position="left">{{ group.label }}</el-divider>
              <div class="model-router-page__node-grid">
                <NodeCard
                  v-for="node in group.nodes"
                  :key="node.id"
                  :node="node"
                  @updated="handleNodeUpdated"
                />
              </div>
              <el-alert v-if="group.nodes.length === 0" type="info" :closable="false" title="暂无节点" />
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-tab-pane>

      <el-tab-pane label="提供商管理" name="providers">
        <ProviderList ref="providerListRef" />
      </el-tab-pane>

      <el-tab-pane label="模型档案" name="profiles">
        <ProfileList ref="profileListRef" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import NodeCard from './components/NodeCard.vue'
import ProviderList from './components/ProviderList.vue'
import ProfileList from './components/ProfileList.vue'
import type { RouterNode } from './api'
import * as api from './api'

const GROUP_DEFS: Array<{ key: string; label: string; match: string[] }> = [
  { key: 'agent', label: 'Agent', match: ['agent'] },
  { key: 'knowledge', label: '知识库', match: ['knowledge', '知识库'] },
  { key: 'tools', label: '工具', match: ['tools', 'tool', '工具'] },
]

const activeTab = ref('nodes')
const nodes = ref<RouterNode[]>([])
const nodesLoading = ref(false)
const activeNodeGroups = ref<string[]>(['agent', 'knowledge', 'tools'])
const reloading = ref(false)
const testingAll = ref(false)

const providerListRef = ref<InstanceType<typeof ProviderList> | null>(null)
const profileListRef = ref<InstanceType<typeof ProfileList> | null>(null)

const healthLabelMap: Record<string, string> = { ok: '正常', degraded: '降级', down: '不可用' }

const overallHealth = computed(() => {
  if (nodes.value.some((n) => n.health === 'down')) return 'down'
  if (nodes.value.some((n) => n.health === 'degraded')) return 'degraded'
  return 'ok'
})
const overallHealthLabel = computed(() => `网关状态：${healthLabelMap[overallHealth.value]}`)

const nodeGroups = computed(() =>
  GROUP_DEFS.map((def) => ({
    key: def.key,
    label: def.label,
    nodes: nodes.value.filter((n) => def.match.some((m) => n.group?.toLowerCase().includes(m.toLowerCase()))),
  })),
)

async function loadNodes() {
  nodesLoading.value = true
  try {
    const r = await api.nodes.list()
    nodes.value = r.nodes
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '节点列表加载失败')
  } finally {
    nodesLoading.value = false
  }
}

function handleNodeUpdated(updated: RouterNode) {
  const idx = nodes.value.findIndex((n) => n.id === updated.id)
  if (idx >= 0) nodes.value[idx] = updated
}

async function handleReload() {
  reloading.value = true
  try {
    const r = await api.reload.trigger()
    ElMessage.success(`配置已重载（档案数：${r.profiles ?? '-'}）`)
    await loadNodes()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '重载失败')
  } finally {
    reloading.value = false
  }
}

async function handleTestAll() {
  testingAll.value = true
  try {
    const r = await api.providers.list()
    const results = await Promise.allSettled(r.providers.map((p) => api.providers.test(p.key)))
    const failed = results.filter((res) => res.status === 'rejected' || (res.status === 'fulfilled' && !res.value.success))
    if (failed.length === 0) {
      ElMessage.success('全部提供商测试通过')
    } else {
      ElMessage.warning(`${failed.length}/${results.length} 个提供商测试未通过`)
    }
    providerListRef.value?.load()
  } catch (e: unknown) {
    ElMessage.error((e as Error).message || '测试全部失败')
  } finally {
    testingAll.value = false
  }
}

onMounted(loadNodes)
</script>

<style scoped>
.model-router-page {
  padding: 16px;
  background: #f5f7fa;
  min-height: 100%;
}
.model-router-page__topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.model-router-page__title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.model-router-page__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c0c4cc;
}
.model-router-page__dot.is-ok { background: #67c23a; }
.model-router-page__dot.is-degraded { background: #e6a23c; }
.model-router-page__dot.is-down { background: #f56c6c; }
.model-router-page__title-text {
  font-size: 16px;
  font-weight: 600;
  color: #1f2937;
}
.model-router-page__actions {
  display: flex;
  gap: 8px;
}
.model-router-page__tabs {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}
.model-router-page__group-title {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}
.model-router-page__group-count {
  margin-left: 8px;
  font-size: 12px;
  color: #9ca3af;
}
.model-router-page__node-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}
</style>
