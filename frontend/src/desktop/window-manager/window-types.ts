import type { Component } from 'vue'

export interface TaskbarItem {
  id: string
  title: string
  icon: string
  isActive: boolean
  minimized: boolean
}

export interface WindowState {
  id: string
  appKey: string
  title: string
  icon: string
  x: number
  y: number
  width: number
  height: number
  zIndex: number
  minimized: boolean
  maximized: boolean
  isActive: boolean
  payload?: Record<string, unknown>
  preMaximizeState?: { x: number; y: number; width: number; height: number }
  windowType?: string
}

export interface FileOpenPayload {
  fileId: number
  fileName: string
  format: string
  page?: number
}

export interface AppRegistryEntry {
  appKey: string
  appName: string
  icon: string
  description: string
  entryComponent: () => Promise<{ default: Component }>
  defaultWidth: number
  defaultHeight: number
  minWidth: number
  minHeight: number
  resizable: boolean
  maximizable: boolean
  singleton: boolean
  showOnDesktop: boolean
  /** Whether to show in system tray (right side of taskbar) */
  showInTray?: boolean
  /** Whether to show in start menu / launcher */
  showInLauncher?: boolean
  /** Whether to show in the right sidebar of desktop */
  showInSidebar?: boolean
  category?: string
  /** List of roles allowed to access this app, defaults to all roles */
  allowedRoles?: string[]
  /** List of file extensions this app supports opening */
  supportedFormats?: string[]
  /** List of file extensions this app can edit or create */
  editableFormats?: string[]
  /** Creatable file type declarations */
  creatableFormats?: Array<{ extension: string; label: string; mime_type?: string }>
  /** Display order, ascending */
  sortOrder?: number
  /** Protocol name for open parameters, defines what type of payload this app accepts */
  openParamProtocol?: string
  windowType?: string
  allowMultiple?: boolean
  capabilities?: {
    canReceiveFile: boolean
    canSendNotification: boolean
    canRunBackground: boolean
    canBeCalledByOther: boolean
  }
  publicActions?: Array<{
    action: string
    description: string
    parameters: Record<string, unknown>
    minRole?: string
  }>
  /** Whether enabled, defaults to enabled */
  enabled?: boolean
}
