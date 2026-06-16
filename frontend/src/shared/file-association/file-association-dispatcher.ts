/**
 * 文件关联分发器
 *
 * 所有文件关联规则从应用注册表派生，注册表是单一的组件键映射与紧急回退源，
 * 而非元数据事实源。元数据事实源是 PostgreSQL system_desktop_apps 表。
 * 此模块保持向后兼容的导出接口。
 */
export {
  getFileAppKey,
  getFileCategoryLabel,
  isFormatEditable,
  getAppByFileFormat,
} from '@/desktop/app-registry/file-association-registry'
