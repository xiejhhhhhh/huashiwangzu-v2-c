export type DesktopEventTypes = {
  'file:uploaded': { folderId?: number; fileName: string }
  'file:deleted': { itemType: 'file' | 'folder'; id: number }
  'file:restored': { itemType: 'file' | 'folder'; id: number }
  'file:renamed': { itemType: 'file' | 'folder'; id: number; newName: string }
  'file:created': { folderId: number; name: string }
  'desktop:create-folder': { folderId?: number | null }
  'desktop:upload-file': { folderId?: number | null }
  'desktop:move-to-folder': { ids: string[]; targetFolderId: string | null }
  'task:completed': { taskId: number | string; taskType: string }
  'notification:created': { id: number; title: string }
  'refresh:file-list': { folderId?: number }
  'refresh:recycle-bin': void
  'app:open': { targetAppKey: string; params?: Record<string, unknown> }
  'app:close': { targetAppKey: string }
  'app:activate': { targetAppKey: string }
  'app:event': { targetAppKey: string; eventName: string; payload?: unknown }
  'app:action': { targetAppKey: string; actionName: string; params?: Record<string, unknown> }
  'app:request': { targetAppId: string; action: string; params: Record<string, unknown>; requestId: string }
  'app:response': { success: boolean; data?: unknown; error?: { code: string; message: string }; requestId?: string }
  'app:notification': { title: string; content: string; type?: string; targetApp?: string }
}
