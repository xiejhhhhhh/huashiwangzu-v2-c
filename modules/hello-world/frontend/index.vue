<template>
  <div class="hello-module">
    <h2>✅ Hello World 模块接入成功</h2>
    <div class="hello-row">运行模式：<b>{{ mode }}</b><span class="hint">（应为 framework）</span></div>
    <div class="hello-row">当前用户：<b>{{ user?.display_name || user?.username || '加载中...' }}</b><span class="hint">（角色：{{ user?.role || '?' }}）</span></div>
    <div class="hello-row">viewer 权限：<b>{{ canView ? '✓ 有' : '✗ 无' }}</b><span class="hint">（runtime 注入生效则为真实角色）</span></div>
    <div class="hello-row">收到的 props payload：<code>{{ JSON.stringify(props) }}</code></div>
    <div class="hello-row">模型档案数：<b>{{ models.length }}</b><span class="hint">（调用 platform.gateway 成功）</span></div>
    <ul class="hello-models">
      <li v-for="m in models" :key="m.key">{{ m.name }} — {{ m.provider }}</li>
    </ul>
    <div v-if="error" class="hello-error">错误：{{ error }}</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { initRuntime, getMode, hasPermission, auth, gateway } from '../runtime'
import type { CurrentUser, ModelProfile } from '../runtime'

interface HelloProps { [key: string]: unknown }
const props = defineProps<HelloProps>()

const mode = ref('')
const user = ref<CurrentUser | null>(null)
const models = ref<ModelProfile[]>([])
const canView = ref(false)
const error = ref('')

onMounted(async () => {
  try {
    await initRuntime('hello-world')
    mode.value = getMode()
    canView.value = hasPermission('viewer')
    user.value = await auth.getCurrentUser()
    models.value = await gateway.listModels()
  } catch (e: unknown) {
    error.value = String((e as { message?: string })?.message || e)
  }
})
</script>

<style scoped>
.hello-module { padding: 24px; font-family: 苹方, 微软雅黑, sans-serif; color: #1f2937; line-height: 1.9; }
.hello-module h2 { margin: 0 0 16px; font-size: 18px; color: #15803d; }
.hello-row { font-size: 14px; }
.hello-row b { color: #1d4ed8; }
.hint { color: #94a3b8; font-size: 12px; margin-left: 6px; }
.hello-row code { background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 12px; }
.hello-models { margin: 8px 0; padding-left: 20px; color: #475569; font-size: 13px; }
.hello-error { margin-top: 12px; color: #dc2626; font-size: 13px; }
</style>
