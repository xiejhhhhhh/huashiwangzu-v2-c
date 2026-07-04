<template>
  <div class="sandbox-shell">
    <header class="sandbox-header">
      <span class="sandbox-badge">SANDBOX</span>
      <h1 class="sandbox-title">AI 助手</h1>
      <span class="sandbox-hint">{{ loggedIn ? 'Independent development mode' : '' }}</span>
    </header>

    <!-- 加载中 -->
    <main v-if="loggedIn === null" class="sandbox-login">
      <div class="login-card" style="text-align:center">
        <p style="color:#909399">正在验证登录状态…</p>
      </div>
    </main>

    <!-- 登录表单：sandbox 没有主框架的登录态，需要独立登录 -->
    <main v-else-if="!loggedIn" class="sandbox-login">
      <div class="login-card">
        <h2>Sandbox 登录</h2>
        <p class="login-hint">Sandbox 运行在独立端口，需要单独登录获取 Token</p>
        <el-form @submit.prevent="doLogin" label-width="0">
          <el-form-item><el-input v-model="username" placeholder="用户名" /></el-form-item>
          <el-form-item><el-input v-model="password" type="password" placeholder="密码" show-password /></el-form-item>
          <el-form-item><el-button type="primary" @click="doLogin" :loading="loginLoading" style="width:100%">登 录</el-button></el-form-item>
        </el-form>
        <p v-if="loginError" class="login-error">{{ loginError }}</p>
      </div>
    </main>

    <main v-else-if="loggedIn" class="sandbox-main">
      <ModuleEntry />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ModuleEntry from '@modules/agent/frontend/index.vue'

const TOKEN_KEY = 'v2_auth_token'
const loggedIn = ref<boolean | null>(null)  // null = 正在验证
const loginLoading = ref(false)
const loginError = ref('')
const username = ref('admin')
const password = ref('')

onMounted(async () => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (!token) { loggedIn.value = false; return }

  // 验证 token 有效性（发一次轻量请求）
  try {
    const r = await fetch('/api/agent/conversations', {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (r.ok) { loggedIn.value = true; return }
  } catch { /* network error — server not running */ }

  // Token 无效或服务没启动 → 清掉，重新显示登录
  localStorage.removeItem(TOKEN_KEY)
  loggedIn.value = false
})

async function doLogin() {
  loginError.value = ''
  loginLoading.value = true
  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value, password: password.value }),
    })
    const body = await r.json()
    if (!body.success) throw new Error(body.error || '登录失败')
    localStorage.setItem(TOKEN_KEY, body.data.access_token)
    loggedIn.value = true
  } catch (e: unknown) {
    loginError.value = e instanceof Error ? e.message : '登录失败'
  } finally {
    loginLoading.value = false
  }
}
</script>

<style scoped>
.sandbox-shell { display: flex; flex-direction: column; height: 100%; }
.sandbox-header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #fff; border-bottom: 1px solid #e4e7ed; flex-shrink: 0; }
.sandbox-badge { display: inline-block; background: #409eff; color: #fff; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 3px; }
.sandbox-title { font-size: 15px; font-weight: 600; color: #303133; }
.sandbox-hint { font-size: 12px; color: #909399; margin-left: auto; }
.sandbox-main { flex: 1; overflow: auto; padding: 16px; }

.sandbox-login { flex: 1; display: flex; align-items: center; justify-content: center; }
.login-card { width: 360px; padding: 32px; background: #fff; border-radius: 8px; box-shadow: 0 2px 12px rgba(0,0,0,0.08); }
.login-card h2 { margin: 0 0 8px; font-size: 18px; color: #303133; }
.login-hint { margin: 0 0 20px; font-size: 13px; color: #909399; }
.login-error { color: #f56c6c; font-size: 13px; text-align: center; }
</style>
