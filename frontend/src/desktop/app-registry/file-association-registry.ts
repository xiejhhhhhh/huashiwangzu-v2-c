import { getAppRegistry } from '@/desktop/app-registry/desktop-app-state'
import { getAllowedApps } from './app-registry'

interface FileAssociationResult {
  appKey: string
  editable: boolean
  分类: string
  categoryLabel: string
}

const categoryLabelMap: Record<string, string> = {
  image: '图片', document: '文档', text: '文本', table: '表格',
  code: '代码', audio: '音频', video: '视频', legacy: '旧格式',
  presentation: '演示', unknown: '未知类型',
}

const legacyCategoryLabelMap: Record<string, string> = {
  doc: 'Word 旧版', xls: 'Excel 旧版', ppt: 'PPT 旧版',
  vsd: 'Visio', vsdx: 'Visio', mpp: 'Project', zip: '压缩包', rar: '压缩包',
}

const 旧格式只读扩展名 = ['doc', 'xls', 'ppt', 'vsd', 'vsdx', 'mpp', 'zip', 'rar']

/** getAppByFileFormat的注册项并计算关联规则，可选按角色过滤 */
export function getAppByFileFormat(格式: string, 角色?: string): FileAssociationResult {
  const ext = (格式 || '').toLowerCase().replace(/^\./, '')
  if (!ext) return { appKey: 'filePreview', editable: false, 分类: 'unknown', categoryLabel: '未知类型' }

  if (旧格式只读扩展名.includes(ext)) {
    return { appKey: 'filePreview', editable: false, 分类: 'legacy', categoryLabel: legacyCategoryLabelMap[ext] || '旧格式' }
  }

  const 应用列表 = 角色 ? getAllowedApps(角色) : Object.values(getAppRegistry())
  for (const app of 应用列表) {
    const 格式列表 = app.supportedFileFormats
    if (!格式列表) continue
    if (格式列表.includes(ext)) {
      const isEditable = app.appKey !== 'filePreview'
      const 分类 = inferFormatCategory(ext, app.appKey)
      return { appKey: app.appKey, editable: isEditable, 分类, categoryLabel: categoryLabelMap[分类] || ext.toUpperCase() }
    }
  }

  return { appKey: 'filePreview', editable: false, 分类: 'unknown', categoryLabel: '未知类型' }
}

function inferFormatCategory(ext: string, appKey: string): string {
  if (appKey === 'filePreview') {
    if (['png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp', 'ico', 'svg'].includes(ext)) return 'image'
    if (['mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a'].includes(ext)) return 'audio'
    if (['mp4', 'webm', 'mov', 'm4v'].includes(ext)) return 'video'
    if (ext === 'pdf') return 'document'
  }
  if (appKey === 'textEditor') return ['txt', 'md'].includes(ext) ? 'text' : 'code'
  if (appKey === 'csvEditor') return 'table'
  if (appKey === 'excelEditor') return 'table'
  if (appKey === 'docxEditor') return 'document'
  if (appKey === 'pptxEditor') return 'presentation'
  return 'document'
}

/** 获取文件关联的应用标识，可选按角色过滤 */
export function getFileAppKey(格式: string, 角色?: string): string {
  return getAppByFileFormat(格式, 角色).appKey
}

/** getFileCategoryLabel，可选按角色过滤 */
export function getFileCategoryLabel(格式: string, 角色?: string): string {
  return getAppByFileFormat(格式, 角色).categoryLabel
}

/** 判断格式是否editable，可选按角色过滤 */
export function isFormatEditable(格式: string, 角色?: string): boolean {
  return getAppByFileFormat(格式, 角色).editable
}
