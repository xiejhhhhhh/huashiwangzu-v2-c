/**
 * Minimal in-session Finder undo stack.
 * Records inverse of move / rename / copy / delete(trash) for ⌘Z.
 */
import { ref } from 'vue'
import {
  copyEntryRequest,
  moveEntryRequest,
  renameEntryRequest,
  restoreRecycleBinEntry,
  moveToRecycleBinRequest,
} from '@/shared/api/desktop'

export type FinderUndoOp =
  | {
      kind: 'move'
      items: Array<{ id: number; type: 'file' | 'folder'; from: number | null; to: number | null }>
    }
  | {
      kind: 'rename'
      itemType: 'file' | 'folder'
      id: number
      prevName: string
      nextName: string
    }
  | {
      kind: 'copy'
      created: Array<{ id: number; type: 'file' | 'folder' }>
    }
  | {
      kind: 'delete'
      items: Array<{ id: number; type: 'file' | 'folder' }>
    }

const stack = ref<FinderUndoOp[]>([])
const MAX = 20

export function pushUndo(op: FinderUndoOp) {
  stack.value = [...stack.value, op].slice(-MAX)
}

export function canUndo() {
  return stack.value.length > 0
}

export async function undoLast(): Promise<{ ok: boolean; message: string }> {
  const op = stack.value[stack.value.length - 1]
  if (!op) return { ok: false, message: '没有可撤销的操作' }
  stack.value = stack.value.slice(0, -1)

  try {
    if (op.kind === 'move') {
      for (const item of op.items) {
        await moveEntryRequest(item.type, item.id, item.from)
      }
      return { ok: true, message: '已撤销移动' }
    }
    if (op.kind === 'rename') {
      await renameEntryRequest(op.itemType, op.id, op.prevName)
      return { ok: true, message: '已撤销重命名' }
    }
    if (op.kind === 'copy') {
      for (const item of op.created) {
        try {
          await moveToRecycleBinRequest(item.type, item.id)
        } catch {
          // ignore single failure
        }
      }
      return { ok: true, message: '已撤销复制（副本移入回收站）' }
    }
    if (op.kind === 'delete') {
      for (const item of op.items) {
        await restoreRecycleBinEntry(item.type, item.id)
      }
      return { ok: true, message: '已撤销删除' }
    }
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : '撤销失败'
    return { ok: false, message: msg }
  }
  return { ok: false, message: '未知操作' }
}

export function clearUndoStack() {
  stack.value = []
}
