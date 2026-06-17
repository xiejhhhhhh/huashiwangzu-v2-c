<template>
  <el-dialog
    :model-value="show"
    title="哪里不好用，直接告诉我们"
    width="520px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <p class="feedback-hint">你遇到了什么问题？我们会认真看每一条反馈。</p>
    <el-form
      ref="formRef"
      :model="feedbackForm"
      :rules="formRules"
      label-width="80px"
      label-position="left"
    >
      <el-form-item label="问题类型" prop="feedbackType">
        <el-select v-model="feedbackForm.feedbackType" placeholder="请选择问题类型" style="width: 100%">
          <el-option
            v-for="(label, value) in feedbackTypeLabels"
            :key="value"
            :label="label"
            :value="value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="问题描述" prop="content">
        <el-input
          v-model="feedbackForm.content"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="请详细描述你遇到的问题或建议"
        />
      </el-form-item>

      <el-form-item label="当前页面">
        <el-input
          :model-value="currentPageUrl"
          disabled
          placeholder="自动获取"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="handleClose">取消</el-button>
      <el-button type="primary" :loading="submitting" @click="submitFeedback">
        提交反馈
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, reactive } from 'vue'
import type { FormInstance } from 'element-plus'
import { ElMessage } from 'element-plus'
import api from '@/shared/api'

const feedbackTypeLabels: Record<string, string> = {
  bug: '功能异常',
  suggestion: '改进建议',
  question: '使用疑问',
  other: '其他',
}

defineProps<{
  show: boolean
}>()

const emit = defineEmits<{
  'submit-success': []
  close: []
}>()

const formRef = ref<FormInstance>()
const submitting = ref(false)
const currentPageUrl = computed(() => window.location.href)

const feedbackForm = reactive({
  feedbackType: '',
  content: '',
})

const formRules = {
  feedbackType: [{ required: true, message: '请选择问题类型', trigger: 'change' }],
  content: [
    { required: true, message: '请填写问题描述', trigger: 'blur' },
    { min: 5, message: '描述至少 5 个字', trigger: 'blur' },
  ],
}

function handleClose() {
  if (!submitting.value) {
    emit('close')
  }
}

async function submitFeedback() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    await api.post('/feedback', {
      feedback_type: feedbackForm.feedbackType,
      content: feedbackForm.content,
      page_url: currentPageUrl.value,
      user_agent: navigator.userAgent,
    })
    ElMessage.success('已经收到，我们会尽快处理')
    feedbackForm.feedbackType = ''
    feedbackForm.content = ''
    formRef.value?.resetFields()
    emit('submit-success')
    emit('close')
  } catch {
    ElMessage.error('提交失败，请稍后重试')
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.feedback-hint {
  color: #909399;
  font-size: 14px;
  margin: 0 0 16px 0;
  padding: 0;
}
</style>
