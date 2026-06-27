<template>
  <div class="approval-panel">
    <header class="ap-header">
      <h2 class="ap-title">敏感操作审批</h2>
      <span class="ap-subtitle">待确认的敏感操作 · 仅管理员</span>
    </header>

    <div v-if="loading" class="ap-loading">加载中...</div>
    <div v-else-if="error" class="ap-error">{{ error }}</div>
    <template v-else>
      <div v-if="approvals.length === 0" class="ap-empty">
        <p>暂无待审批的操作</p>
      </div>

      <div v-for="a in approvals" :key="a.id" class="ap-card">
        <div class="ap-card-header">
          <span class="ap-badge-pending">待审批</span>
          <span class="ap-tool-name">{{ a.tool_name }}</span>
        </div>
        <div class="ap-card-meta">
          <span>Agent: {{ a.agent_code || '-' }}</span>
          <span>请求者: {{ a.requested_by }}</span>
          <span>时间: {{ a.created_at }}</span>
          <span v-if="a.conversation_id">对话: #{{ a.conversation_id }}</span>
        </div>
        <div class="ap-card-actions">
          <button class="ap-btn ap-btn-approve" @click="resolve(a.id, 'approved')" :disabled="resolving === a.id">同意</button>
          <button class="ap-btn ap-btn-reject" @click="showRejectDialog(a.id)" :disabled="resolving === a.id">拒绝</button>
        </div>
      </div>

      <!-- 拒绝原因对话框 -->
      <div v-if="rejectId" class="ap-dialog-overlay" @click.self="rejectId = null">
        <div class="ap-dialog">
          <h3>拒绝操作</h3>
          <p>工具: {{ currentApproval?.tool_name }}</p>
          <textarea v-model="rejectReason" placeholder="拒绝原因（可选）" rows="3" class="ap-textarea"></textarea>
          <div class="ap-dialog-actions">
            <button class="ap-btn ap-btn-reject" @click="doReject" :disabled="resolving === rejectId">确认拒绝</button>
            <button class="ap-btn" @click="rejectId = null">取消</button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiGet, apiPost } from '../../runtime'

interface ApprovalItem {
  id: number
  agent_code: string
  tool_name: string
  tool_args: string | null
  status: string
  requested_by: number
  conversation_id: number | null
  created_at: string | null
}


const loading = ref(true)
const error = ref('')
const approvals = ref<ApprovalItem[]>([])
const resolving = ref<number | null>(null)
const rejectId = ref<number | null>(null)
const rejectReason = ref('')

const currentApproval = computed(() => approvals.value.find(a => a.id === rejectId.value))

async function loadApprovals() {
  loading.value = true; error.value = ''
  try {
    approvals.value = await apiGet<ApprovalItem[]>('/agent/admin/approvals/pending')
  } catch (e: unknown) {
    error.value = String((e as Error).message || e)
  } finally {
    loading.value = false
  }
}

async function resolve(approvalId: number, decision: string) {
  resolving.value = approvalId
  try {
    await apiPost(`/agent/admin/approvals/${approvalId}/resolve`, { decision })
    approvals.value = approvals.value.filter(a => a.id !== approvalId)
    alert(decision === 'approved' ? '已同意' : '已拒绝')
  } catch (e: unknown) {
    alert(String((e as Error).message || e))
  } finally {
    resolving.value = null
  }
}

function showRejectDialog(approvalId: number) {
  rejectId.value = approvalId
  rejectReason.value = ''
}

async function doReject() {
  if (!rejectId.value) return
  resolving.value = rejectId.value
  try {
    await apiPost(`/agent/admin/approvals/${rejectId.value}/resolve`, { decision: 'rejected', reason: rejectReason.value || null })
    approvals.value = approvals.value.filter(a => a.id !== rejectId.value)
    rejectId.value = null
    alert('已拒绝')
  } catch (e: unknown) {
    alert(String((e as Error).message || e))
  } finally {
    resolving.value = null
  }
}

onMounted(loadApprovals)
</script>

<style scoped>
.approval-panel {
  --ap-primary: #2395bc;
  --ap-primary-light: #e8f6fb;
  --ap-bg: #f7f9fa;
  --ap-card-bg: #ffffff;
  --ap-text: #1a1a1a;
  --ap-text-secondary: #5e5e5e;
  --ap-border: #e2e6e9;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Microsoft YaHei', 'Helvetica Neue', sans-serif;
  font-size: 13px;
  color: var(--ap-text);
  background: var(--ap-bg);
  height: 100%;
  overflow-y: auto;
  padding: 20px 24px;
}
.ap-header { margin-bottom: 20px; display: flex; align-items: baseline; gap: 12px; }
.ap-title { font-size: 18px; font-weight: 600; margin: 0; color: var(--ap-text); }
.ap-subtitle { font-size: 12px; color: var(--ap-text-secondary); }
.ap-loading, .ap-error { padding: 40px; text-align: center; color: var(--ap-text-secondary); }
.ap-error { color: #f56c6c; }
.ap-empty { padding: 60px 40px; text-align: center; color: var(--ap-text-secondary); }

.ap-card {
  background: var(--ap-card-bg);
  border: 1px solid var(--ap-border);
  border-radius: 6px;
  padding: 14px 16px;
  margin-bottom: 12px;
}
.ap-card-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.ap-badge-pending {
  background: #fff3cd; color: #856404;
  padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600;
}
.ap-tool-name { font-weight: 600; font-size: 14px; font-family: 'SF Mono', monospace; }
.ap-card-meta { display: flex; gap: 16px; font-size: 11px; color: var(--ap-text-secondary); margin-bottom: 10px; flex-wrap: wrap; }
.ap-card-actions { display: flex; gap: 8px; }
.ap-btn {
  height: 30px; padding: 0 14px; border: 1px solid var(--ap-border);
  background: var(--ap-card-bg); color: var(--ap-text);
  border-radius: 4px; font-size: 12px; cursor: pointer;
}
.ap-btn:hover { border-color: var(--ap-primary); }
.ap-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.ap-btn-approve { background: #e1f3e1; color: #1f7a1f; border-color: #c6e6c6; }
.ap-btn-approve:hover { background: #c6e6c6; }
.ap-btn-reject { background: #fef0f0; color: #f56c6c; border-color: #fce4e4; }
.ap-btn-reject:hover { background: #fce4e4; }

/* Dialog */
.ap-dialog-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.3);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.ap-dialog { background: #fff; border-radius: 8px; padding: 24px; min-width: 360px; max-width: 480px; }
.ap-dialog h3 { margin: 0 0 12px; font-size: 16px; }
.ap-dialog p { margin: 0 0 12px; font-size: 13px; color: var(--ap-text-secondary); }
.ap-textarea {
  width: 100%; padding: 8px; border: 1px solid var(--ap-border);
  border-radius: 4px; font-size: 13px; resize: vertical; box-sizing: border-box;
  font-family: inherit;
}
.ap-dialog-actions { display: flex; gap: 8px; margin-top: 16px; justify-content: flex-end; }
</style>
