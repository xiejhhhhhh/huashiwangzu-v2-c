import { ref, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { 获取角色矩阵, 保存角色矩阵 } from '@/shared/api/settings'
import type { 角色矩阵项 } from '@/shared/api/types'

export function use角色矩阵() {
  const 角色矩阵保存中 = ref(false)
  const 角色矩阵 = ref<角色矩阵项[]>([])

  async function 加载角色矩阵() {
    try { const res = await 获取角色矩阵(); if (res.success) 角色矩阵.value = res.数据.矩阵 }
    catch (e: any) { ElMessage.error(e?.error || '加载角色矩阵失败') }
  }

  async function 保存角色矩阵表单() {
    角色矩阵保存中.value = true
    try { const res = await 保存角色矩阵(角色矩阵.value); if (res.success) ElMessage.success('角色矩阵已保存'); else ElMessage.error(res.error || '保存失败') }
    finally { 角色矩阵保存中.value = false }
  }

  onMounted(() => { 加载角色矩阵() })

  return {
    角色矩阵保存中, 角色矩阵, 保存角色矩阵表单, 加载角色矩阵,
  }
}
