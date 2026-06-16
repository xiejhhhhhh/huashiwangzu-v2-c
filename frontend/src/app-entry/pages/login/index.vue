<template>
  <div class="登录页">
    <div class="登录卡片">
      <div class="登录图标">
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none">
          <rect width="48" height="48" rx="12" fill="#00b4d8"/>
          <text x="24" y="30" text-anchor="middle" fill="#fff" font-size="20" font-weight="700">H</text>
        </svg>
      </div>
      <h1 class="登录标题">华世王镞</h1>
      <p class="登录副标题">企业管理系统</p>
      <el-form ref="表单" :model="表单数据" :rules="校验规则" @submit.prevent="提交登录" style="margin-top: 32px;">
        <el-form-item prop="用户名">
          <el-input v-model="表单数据.用户名" placeholder="用户名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item prop="密码">
          <el-input v-model="表单数据.密码" type="password" placeholder="密码" size="large" :prefix-icon="Lock" show-password />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" size="large" native-type="submit" :loading="加载中" @click="提交登录" style="width: 100%; font-size: 15px; letter-spacing: 2px;">
            {{ 加载中 ? '登录中...' : '登 录' }}
          </el-button>
        </el-form-item>
      </el-form>
      <div v-if="错误提示" style="margin-top: 16px;">
        <el-alert :title="错误提示" type="error" show-icon :closable="false" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { User, Lock } from '@element-plus/icons-vue'
import { useUserStore } from '@/platform/stores/user'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const store = useUserStore()
const 表单 = ref<FormInstance>()
const 加载中 = ref(false)
const 错误提示 = ref('')

const 表单数据 = reactive({
  用户名: '',
  密码: '',
})

const 校验规则: FormRules = {
  用户名: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  密码: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function 提交登录() {
  if (!表单.value) return
  const valid = await 表单.value.validate().catch(() => false)
  if (!valid) return

  加载中.value = true
  错误提示.value = ''

  try {
    const res = await store.登录(表单数据.用户名, 表单数据.密码)
    if (res.success) {
      router.push('/desktop')
    } else {
      错误提示.value = res.error || '登录失败'
    }
  } catch (e: any) {
    错误提示.value = e?.error || '登录失败，请稍后重试'
  } finally {
    加载中.value = false
  }
}
</script>
