import startPng from '@/assets/desktop-icons/start.png'
import filePng from '@/assets/desktop-icons/file.png'
import recycleBinPng from '@/assets/desktop-icons/recycle-bin.png'
import wordPng from '@/assets/desktop-icons/Word.png'
import excelPng from '@/assets/desktop-icons/Excel.png'
import powerPointPng from '@/assets/desktop-icons/PowerPoint.png'
import notepadPng from '@/assets/desktop-icons/notepad.png'
import videoPng from '@/assets/desktop-icons/video.png'
import uploadPng from '@/assets/desktop-icons/upload.png'
import downloadPng from '@/assets/desktop-icons/download.png'
import notificationPng from '@/assets/desktop-icons/notification.png'
import fileManagerIcon from '@fluentui/svg-icons/icons/document_folder_24_color.svg?raw'
import recycleBinIcon from '@fluentui/svg-icons/icons/recycle_32_filled.svg?raw'
import libraryIcon from '@fluentui/svg-icons/icons/library_32_color.svg?raw'
import botIcon from '@fluentui/svg-icons/icons/bot_24_color.svg?raw'
import settingsIcon from '@fluentui/svg-icons/icons/settings_48_color.svg?raw'
import taskIcon from '@fluentui/svg-icons/icons/task_list_square_ltr_48_filled.svg?raw'
import dashboardIcon from '@fluentui/svg-icons/icons/data_bar_vertical_ascending_20_filled.svg?raw'
import previewIcon from '@fluentui/svg-icons/icons/document_48_color.svg?raw'
import editIcon from '@fluentui/svg-icons/icons/edit_24_color.svg?raw'
import gridIcon from '@fluentui/svg-icons/icons/grid_24_filled.svg?raw'
import copyIcon from '@fluentui/svg-icons/icons/document_copy_24_filled.svg?raw'
import documentIcon from '@fluentui/svg-icons/icons/document_24_color.svg?raw'
import panelIcon from '@fluentui/svg-icons/icons/board_24_color.svg?raw'
import { moduleIconAssets } from './module-icon-assets.generated'

const svgMap: Record<string, string> = {
  Files: fileManagerIcon, Delete: recycleBinIcon, Collection: libraryIcon,
  ChatDotRound: botIcon, Setting: settingsIcon, List: taskIcon,
  Dashboard: dashboardIcon, View: previewIcon, EditPen: editIcon,
  Grid: gridIcon, DocumentCopy: copyIcon, Document: documentIcon,
  DataBoard: panelIcon,
}

const imageMap: Record<string, string> = {
  Start: startPng,
  Files: filePng, FolderOpened: filePng,
  Delete: recycleBinPng,
  Document: wordPng,
  DocumentCopy: excelPng,
  DataBoard: powerPointPng,
  Edit: notepadPng, EditPen: notepadPng,
  View: videoPng,
  Upload: uploadPng,
  Download: downloadPng,
  Bell: notificationPng,
  ...moduleIconAssets,
}

export function getAppSVG(icon: string): string {
  return svgMap[icon] || fileManagerIcon
}

export function getAppImage(icon: string): string {
  return imageMap[icon] || ''
}
