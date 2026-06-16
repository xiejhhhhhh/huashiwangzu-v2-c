import { 友好化错误信息 } from '@/shared/composables/use-friendly-error'

export function 获取错误信息(error: unknown) {
  const 响应错误 = error as { config?: { url?: string }; response?: { status?: number; data?: Record<string, any> } }
  const 状态码 = 响应错误.response?.status
  const 响应数据 = 响应错误.response?.data
  const 是登录请求 = 响应错误.config?.url?.endsWith('/login') === true
  if (!响应错误.response) return { success: false, 数据: null, error: '网络连接异常，请检查公司网络' }

  let 错误信息 = ''
  if (状态码 === 401 && 是登录请求) {
    错误信息 = 友好化错误信息(响应数据?.error || 响应数据?.error || '用户名或密码错误')
  } else if (状态码 === 401) {
    错误信息 = '登录已过期，请重新登录'
  } else if (状态码 === 403) {
    错误信息 = '你没有权限操作这个内容'
  } else if (状态码 === 404) {
    错误信息 = '内容不存在或已被删除'
  } else if (状态码 === 502) {
    错误信息 = '后端服务暂时不可用，请检查 scripts/start_backend.sh 是否已运行'
  } else if (状态码 && 状态码 >= 500) {
    错误信息 = '系统开小差了，请联系管理员'
  } else {
    错误信息 = 友好化错误信息(响应数据?.error || 响应数据?.error || '请求失败，请稍后重试')
  }
  return { success: false, 数据: 响应数据?.data ?? 响应数据?.data ?? null, error: 错误信息 }
}

export function 转中文(数据: any): any {
  if (!数据 || typeof 数据 !== 'object') return 数据
  if (Array.isArray(数据)) return 数据.map(转中文)

  const 映射: Record<string, string> = {
    success: '成功', data: '数据', error: '错误', errors: '错误详情',
    list: '列表', items: '列表', total: '总数', count: '数量',
    page: '页码', page_size: '每页数量', pageSize: '每页数量',
    unread_count: '未读数', ok: 'ok',
    app_id: '应用标识', name: '名称', icon: '图标',
    description: '描述', entry_component_key: '入口组件键',
    default_width: '默认宽度', default_height: '默认高度',
    singleton: '单例', category: '分类',
    username: '用户名', display_name: 'displayName', role: '角色',
    access_token: '访问令牌', token_type: '令牌类型',
    id: 'id', file_name: '文件名', extension: '格式',
    file_size: '文件大小', folder_id: '文件夹id',
    mime_type: 'MIME类型', owner_id: '拥有者id',
    parent_id: '父文件夹id', status: '状态',
    window_type: '窗口类型', min_width: '最小宽度', min_height: '最小高度',
    allow_multiple: '允许多开', allowed_roles: '允许角色',
    item_type: '类型', origin_id: '原始id',
    page_id: '页ID', page_num: '页码', pageNum: '页码', page_count: '页数',
    catalog_id: '文件ID', file_id: '文件ID', package_id: '包ID',
    catalogId: '文件ID', fileId: '文件ID', packageId: '包ID',
    notification_type: '通知类型', publisher_id: '发布人ID',
    feedback_type: '反馈类型', admin_note: '处理备注', handled_at: '处理时间',
    page_url: '当前页面', user_agent: '浏览器信息',
    deleted_at: '删除时间', created_at: '创建时间',
    updated_at: '更新时间', message: '消息',
    standardName: '标准名', entityType: '实体类型',
    confirmStatus: '状态', occurrenceCount: '出现次数',
    entityId: '词典ID', aliasType: '别名类型',
    sourceType: '证据类型', sourceId: '内容块ID',
    confidence: '置信度', crossVerified: '已交叉验证',
    boundConclusions: '结论列表', createdAt: '创建时间',
    content: '候选原文', source: '来源方式',
    evidencePage: '原文片段', verdictStatus: '状态',
    nodeCount: '节点数', edgeCount: '边数', latestNodes: '最新节点',
    node: '节点', edges: '边列表', entity: '实体',
    fromNodeId: '起点ID', toNodeId: '终点ID',
    supportChunkIds: '支持块ID列表',
    fusion_id: '融合ID', fusion_text: '融合正文',
    summary: '页面摘要', quality_score: '质量分',
    original_sources: '来源列表',
    page_sources: '页源数量', page_fusions: '页融合数量',
  }

  const 结果: Record<string, any> = {}
  for (const [英文, 值] of Object.entries(数据)) {
    const 中文名 = 映射[英文] || 英文
    结果[中文名] = 转中文(值)
    if (英文 === 'name') 结果['应用名'] = 转中文(值)
    if (英文 === 'id') 结果['ID'] = 转中文(值)
    if (英文 === 'id') {
      结果['词典ID'] ??= 转中文(值)
      结果['证据ID'] ??= 转中文(值)
      结果['候选ID'] ??= 转中文(值)
    }
    if (英文 === 'count') 结果['待校准数'] ??= 转中文(值)
  }
  if (结果.format !== undefined && 结果.是否为文件夹 === undefined) 结果.是否为文件夹 = false
  return 结果
}
