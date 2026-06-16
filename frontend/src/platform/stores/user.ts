import { defineStore } from 'pinia'
import { ref } from 'vue'
import { 登录请求, fetchCurrentUser请求, 登出请求 } from '@/shared/api/auth'
import type { 用户信息 } from '@/shared/api/types'

export const useUserStore = defineStore('用户', () => {
  const 用户信息 = ref<用户信息 | null>(null)
  const 已登录 = ref(false)
  const 加载中 = ref(false)
  const 已检查过 = ref(false)

  async function fetchCurrentUser() {
    if (已检查过.value) return
    已检查过.value = true
    加载中.value = true
    try {
      const res = await fetchCurrentUser请求()
      if (已登录.value) return
      if (res.success) {
        if (res.data != null) 用户信息.value = res.data
        已登录.value = true
      }
    } catch {
      用户信息.value = null
      已登录.value = false
    } finally {
      加载中.value = false
    }
  }

  function resetCheck() {
    已检查过.value = false
    用户信息.value = null
    已登录.value = false
  }

  async function 登录(用户名: string, 密码: string) {
    try {
    const res = await 登录请求({ username: 用户名, password: 密码 })
      if (res.success) {
      const loginData = res.data as any
      if (loginData?.user) 用户信息.value = loginData.user
        已登录.value = true
      }
      return res
    } catch (e: any) {
      return e
    }
  }

  async function 登出() {
    try {
      await 登出请求()
    } catch {
      // 忽略登出请求错误
    }
    localStorage.removeItem('v2_auth_token')
    用户信息.value = null
    已登录.value = false
    已检查过.value = false
  }

  return { 用户信息, 已登录, 加载中, 已检查过, fetchCurrentUser, resetCheck, 登录, 登出 }
})
