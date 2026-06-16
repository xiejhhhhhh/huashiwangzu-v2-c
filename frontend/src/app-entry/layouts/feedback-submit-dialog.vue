<template>
  <el-dialog
    :model-value="显示"
    title="哪里不好用，直接告诉我们"
    width="520px"
    :close-on-click-modal="false"
    @close="关闭弹窗"
  >
    <p class="反馈提示">你遇到了什么问题？我们会认真看每一条反馈。</p>
    <el-form
      ref="表单ref"
      :model="反馈表单"
      :rules="表单规则"
      label-width="80px"
      label-position="left"
    >
      <el-form-item label="问题类型" prop="反馈类型">
        <el-select v-model="反馈表单.反馈类型" placeholder="请选择问题类型" style="width: 100%">
          <el-option
            v-for="(标签, 值) in 反馈类型映射"
            :key="值"
            :label="标签"
            :value="值"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="问题描述" prop="反馈内容">
        <el-input
          v-model="反馈表单.反馈内容"
          type="textarea"
          :rows="4"
          maxlength="2000"
          show-word-limit
          placeholder="请详细描述你遇到的问题或建议"
        />
      </el-form-item>

      <el-form-item label="当前页面">
        <el-input
          :model-value="当前页面地址"
          disabled
          placeholder="自动获取"
        />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="关闭弹窗">取消</el-button>
      <el-button type="primary" :loading="提交中" @click="提交反馈">
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

const 反馈类型映射: Record<string, string> = {
  'bug': '功能异常',
  'suggestion': '改进建议',
  'question': '使用疑问',
  'other': '其他',
}

const props = defineProps<{
  显示: boolean
}>()

const emit = defineEmits<{
  提交success: []
  关闭: []
}>()

const 表单ref = ref<FormInstance>()
const 提交中 = ref(false)
const 当前页面地址 = computed(() => window.location.href)

const 反馈表单 = reactive({
  反馈类型: '',
  反馈内容: '',
})

const 表单规则 = {
  反馈类型: [{ required: true, message: '请选择问题类型', trigger: 'change' }],
  反馈内容: [
    { required: true, message: '请填写问题描述', trigger: 'blur' },
    { min: 5, message: '描述至少 5 个字', trigger: 'blur' },
  ],
}

function 关闭弹窗() {
  if (!提交中.value) {
    emit('关闭')
  }
}

async function 提交反馈() {
  const 有效 = await 表单ref.value?.validate().catch(() => false)
  if (!有效) return

  提交中.value = true
  try {
    await api.post('/feedback', {
      feedback_type: 反馈表单.反馈类型,
      content: 反馈表单.反馈内容,
      page_url: 当前页面地址.value,
      user_agent: navigator.userAgent,
    })
    ElMessage.success('已经收到，我们会尽快处理')
    反馈表单.反馈类型 = ''
    反馈表单.反馈内容 = ''
    表单ref.value?.resetFields()
    emit('提交success')
    emit('关闭')
  } catch {
    ElMessage.error('提交失败，请稍后重试')
  } finally {
    提交中.value = false
  }
}
</script>

<style scoped>
.反馈提示 {
  color: #909399;
  font-size: 14px;
  margin: 0 0 16px 0;
  padding: 0;
}
</style>
