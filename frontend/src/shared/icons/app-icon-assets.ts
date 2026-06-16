import 开始PNG from '@/assets/desktop-icons/start.png'
import 文件PNG from '@/assets/desktop-icons/file.png'
import 回收站PNG from '@/assets/desktop-icons/recycle-bin.png'
import 知识库PNG from '@/assets/desktop-icons/knowledge-base.png'
import AIPNG from '@/assets/desktop-icons/ai-assistant.png'
import WordPNG from '@/assets/desktop-icons/Word.png'
import ExcelPNG from '@/assets/desktop-icons/Excel.png'
import PowerPointPNG from '@/assets/desktop-icons/PowerPoint.png'
import 记事本PNG from '@/assets/desktop-icons/notepad.png'
import 视频PNG from '@/assets/desktop-icons/video.png'
import 上传PNG from '@/assets/desktop-icons/upload.png'
import 下载PNG from '@/assets/desktop-icons/download.png'
import 通知PNG from '@/assets/desktop-icons/notification.png'
import 文件管理图标 from '@fluentui/svg-icons/icons/document_folder_24_color.svg?raw'
import 回收站图标 from '@fluentui/svg-icons/icons/recycle_32_filled.svg?raw'
import 知识库图标 from '@fluentui/svg-icons/icons/library_32_color.svg?raw'
import Agent图标 from '@fluentui/svg-icons/icons/bot_24_color.svg?raw'
import 设置图标 from '@fluentui/svg-icons/icons/settings_48_color.svg?raw'
import 任务图标 from '@fluentui/svg-icons/icons/task_list_square_ltr_48_filled.svg?raw'
import 仪表盘图标 from '@fluentui/svg-icons/icons/data_bar_vertical_ascending_20_filled.svg?raw'
import 预览图标 from '@fluentui/svg-icons/icons/document_48_color.svg?raw'
import 编辑图标 from '@fluentui/svg-icons/icons/edit_24_color.svg?raw'
import 网格图标 from '@fluentui/svg-icons/icons/grid_24_filled.svg?raw'
import 复制图标 from '@fluentui/svg-icons/icons/document_copy_24_filled.svg?raw'
import 文档图标 from '@fluentui/svg-icons/icons/document_24_color.svg?raw'
import 面板图标 from '@fluentui/svg-icons/icons/board_24_color.svg?raw'

const SVG映射: Record<string, string> = {
  Files: 文件管理图标, Delete: 回收站图标, Collection: 知识库图标,
  ChatDotRound: Agent图标, Setting: 设置图标, List: 任务图标,
  Dashboard: 仪表盘图标, View: 预览图标, EditPen: 编辑图标,
  Grid: 网格图标, DocumentCopy: 复制图标, Document: 文档图标,
  DataBoard: 面板图标,
}

const 图片映射: Record<string, string> = {
  Start: 开始PNG,
  Files: 文件PNG, FolderOpened: 文件PNG,
  Delete: 回收站PNG,
  Collection: 知识库PNG,
  ChatDotRound: AIPNG, MagicStick: AIPNG,
  Document: WordPNG,
  DocumentCopy: ExcelPNG,
  DataBoard: PowerPointPNG,
  Edit: 记事本PNG, EditPen: 记事本PNG,
  View: 视频PNG,
  Upload: 上传PNG,
  Download: 下载PNG,
  Bell: 通知PNG,
}

export function getAppSVG(图标: string): string {
  return SVG映射[图标] || 文件管理图标
}

export function getApp图片(图标: string): string {
  return 图片映射[图标] || ''
}
