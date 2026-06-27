<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-icon">
        <el-icon :size="56" color="var(--primary-color)"><Monitor /></el-icon>
      </div>
      <h1 class="login-title">华世王镞</h1>
      <p class="login-subtitle">企业管理系统</p>
      <el-form ref="formRef" :model="formData" :rules="formRules" @submit.prevent="submitLogin" style="margin-top: 32px;">
        <el-form-item prop="username">
          <el-input v-model="formData.username" placeholder="用户名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="password">
          <el-input v-model="formData.password" type="password" placeholder="密码" size="large" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" native-type="submit" :loading="isLoading" @click="submitLogin" style="width: 100%; font-size: 15px; letter-spacing: 2px;">
            {{ isLoading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="errorMessage" style="margin-top: 16px;">
        <el-alert :title="errorMessage" type="error" show-icon :closable="false" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock, Monitor } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import { useUserStore } from '@/platform/stores/user'

const router = useRouter()
const store = useUserStore()

const formRef = ref<FormInstance>()
const isLoading = ref(false)
const errorMessage = ref('')
const formData = reactive({
  username: '',
  password: '',
})
const formRules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function submitLogin() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return
  isLoading.value = true
  errorMessage.value = ''
  try {
    const res = await store.login(formData.username, formData.password)
    if (res.success) {
      ElMessage.success('登录成功')
      await router.push('/desktop')
    } else {
      errorMessage.value = res.error || '登录失败'
    }
  } catch (e: unknown) {
    errorMessage.value = (e as {error?: string})?.error || '登录失败，请稍后重试'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.login-page { display: flex; align-items: center; justify-content: center; min-height: 100vh; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); }
.login-card { background: #fff; border-radius: 16px; padding: 48px 40px; width: 420px; max-width: 90vw; box-shadow: 0 20px 60px rgba(0,0,0,.15); text-align: center; }
.login-icon { margin-bottom: 8px; }
.login-title { margin: 0; font-size: 26px; font-weight: 700; color: #0f172a; }
.login-subtitle { margin: 4px 0 0; font-size: 14px; color: #94a3b8; }
</style>
