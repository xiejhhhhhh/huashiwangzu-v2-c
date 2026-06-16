import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { 获取系统配置, 保存系统配置 } from '@/shared/api/settings'
import type { 系统配置数据 } from '@/shared/api/types'

export function use系统配置() {
  const 系统配置保存中 = ref(false)
  const 系统配置表单 = ref<系统配置数据>({ 项目名称: '', 系统版本: '', 登录页标题: '', 默认角色: 'viewer' })

  async function 加载系统配置() {
    try { const res = await 获取系统配置(); if (res.success) 系统配置表单.value = res.数据 }
    catch (e: any) { ElMessage.error(e?.error || '加载系统配置失败') }
  }

  async function 保存系统配置表单() {
    系统配置保存中.value = true
    try { const res = await 保存系统配置(系统配置表单.value); if (res.success) ElMessage.success('系统配置已保存'); else ElMessage.error(res.error || '保存失败') }
    finally { 系统配置保存中.value = false }
  }

  onMounted(() => { 加载系统配置() })

  return {
    系统配置保存中, 系统配置表单, 保存系统配置表单, 加载系统配置,
  }
}
