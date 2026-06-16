import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 获取用户列表, 搜索用户, 创建用户, 编辑用户, 禁用用户 } from '@/shared/api/settings'
import type { UserEntry } from '@/shared/api/settings'

export function use用户管理() {
  const 用户列表 = ref<UserEntry[]>([])
  const 加载中 = ref(false)
  const 搜索词 = ref('')
  const 弹窗可见 = ref(false)
  const 弹窗模式 = ref<'新建' | '编辑'>('新建')
  const 提交中 = ref(false)
  const 编辑目标 = ref<UserEntry | null>(null)
  const 表单 = ref({ 用户名: '', 密码: '', displayName: '', email: '', 角色: 'viewer' as string })

  function 角色名称(角色: string) { return { admin: '管理员', editor: '编辑者', viewer: '查看者' }[角色] || 角色 }
  function 角色类型(角色: string) { return { admin: 'danger', editor: 'primary', viewer: 'info' }[角色] || 'info' }

  async function 加载用户() {
    加载中.value = true
    try { const res = await 获取用户列表(); if (res.success) 用户列表.value = res.data.用户列表 }
    catch (e: any) { ElMessage.error(e?.error || '获取用户列表失败') }
    finally { 加载中.value = false }
  }

  async function 执行搜索() {
    if (!搜索词.value.trim()) { 加载用户(); return }
    加载中.value = true
    try { const res = await 搜索用户(搜索词.value.trim()); if (res.success) 用户列表.value = res.data.用户列表 }
    catch (e: any) { ElMessage.error(e?.error || '搜索失败') }
    finally { 加载中.value = false }
  }

  function 打开弹窗(模式: '新建' | '编辑', 用户?: UserEntry) {
    弹窗模式.value = 模式
    if (模式 === '编辑' && 用户) { 编辑目标.value = 用户; 表单.value = { 用户名: '', 密码: '', displayName: 用户.displayName || '', email: 用户.email || '', 角色: 用户.角色 || 'viewer' } }
    else { 表单.value = { 用户名: '', 密码: '', displayName: '', email: '', 角色: 'viewer' } }
    弹窗可见.value = true
  }

  async function 提交表单() {
    if (弹窗模式.value === '新建') {
      if (!表单.value.用户名 || !表单.value.密码) { ElMessage.warning('用户名和密码为必填'); return }
      提交中.value = true
      try { const res = await 创建用户(表单.value); if (res.success) { ElMessage.success('创建成功'); 弹窗可见.value = false; 加载用户() } else ElMessage.error(res.error || '创建失败') }
      catch (e: any) { ElMessage.error(e?.error || '创建失败') }
      finally { 提交中.value = false }
    } else {
      提交中.value = true
      try { const res = await 编辑用户({ 用户id: 编辑目标.value!.id, displayName: 表单.value.displayName, email: 表单.value.email, 角色: 表单.value.角色, 密码: 表单.value.密码 || undefined }); if (res.success) { ElMessage.success(表单.value.密码 ? '密码已重置成功，请将新密码告知用户' : '修改成功'); 弹窗可见.value = false; 加载用户() } else ElMessage.error(res.error || '修改失败') }
      catch (e: any) { ElMessage.error(e?.error || '修改失败') }
      finally { 提交中.value = false }
    }
  }

  async function 切换状态(用户: UserEntry) {
    const 动作 = 用户.状态 === 1 ? '禁用' : '启用'
    try { await ElMessageBox.confirm(`确认${动作}用户「${用户.用户名}」？`, '提示') } catch { return }
    try { const res = await 禁用用户(用户.id); if (res.success) { ElMessage.success(`${动作}成功`); 加载用户() } else ElMessage.error(res.error || `${动作}失败`) }
    catch (e: any) { ElMessage.error(e?.error || `${动作}失败`) }
  }

  onMounted(() => { 加载用户() })

  return {
    用户列表, 加载中, 搜索词, 弹窗可见, 弹窗模式, 提交中, 表单,
    角色名称, 角色类型, 加载用户, 执行搜索, 打开弹窗, 提交表单, 切换状态,
  }
}
