import { reactive, ref } from 'vue'
import { keepaliveFetch } from '@/shared/api'
import { readDesktopStateRequest, saveDesktopStateRequest } from '@/shared/api/desktop'
import { deduplicateSnapshots, type DesktopWindowSnapshot } from './desktop-session-storage'

export interface DesktopPersistentState {
  version: number
  windows: DesktopWindowSnapshot[]
  appState: Record<string, Record<string, unknown>>
  iconPositions: Record<string, { col?: number; row?: number; x: number; y: number }>
}

const state = reactive<DesktopPersistentState>({ version: 1, windows: [], appState: {}, iconPositions: {} })
const loaded = ref(false)
let saveTimer: ReturnType<typeof setTimeout> | null = null
/** framework_desktop_states.version CAS 游标 */
let serverVersion = 0

export async function loadDesktopState() {
  try {
    const envelope = await readDesktopStateRequest()
    state.windows = Array.isArray(envelope.state.windows) ? envelope.state.windows : []
    state.appState = envelope.state.appState || {}
    state.iconPositions = envelope.state.iconPositions || {}
    state.version = envelope.state.version ?? 1
    serverVersion = Number(envelope.serverVersion || 0) || 0
  } catch {
    serverVersion = 0
  }
  loaded.value = true
  return state
}

export function updateWindowSnapshot(windows: DesktopWindowSnapshot[]) {
  state.windows = deduplicateSnapshots(windows)
  scheduleDesktopStateSave()
}

export function readAppState<T>(appKey: string, stateName: string, defaultValue: T): T {
  return (state.appState[appKey]?.[stateName] as T | undefined) ?? defaultValue
}

export function updateAppState(appKey: string, stateName: string, value: unknown) {
  if (!state.appState[appKey]) state.appState[appKey] = {}
  state.appState[appKey][stateName] = value
  scheduleDesktopStateSave()
}

export function scheduleDesktopStateSave() {
  if (!loaded.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(saveDesktopStateNow, 180)
}

export async function saveDesktopStateNow() {
  if (!loaded.value) return
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = null
  try {
    const expected = serverVersion > 0 ? serverVersion : undefined
    const envelope = await saveDesktopStateRequest(JSON.parse(JSON.stringify(state)), expected)
    serverVersion = Number(envelope.serverVersion || (serverVersion + 1)) || (serverVersion + 1)
    state.version = envelope.state.version ?? serverVersion
  } catch (err: unknown) {
    const msg = String((err as { error?: string; message?: string })?.error
      || (err as { message?: string })?.message
      || err
      || '')
    if (msg.includes('DESKTOP_STATE_CONFLICT') || msg.includes('409') || msg.includes('conflict')) {
      try { await loadDesktopState() } catch { /* ignore */ }
    }
  }
}

export function saveDesktopStateWithKeepalive() {
  if (!loaded.value) return
  const expected = serverVersion > 0 ? serverVersion : undefined
  const { version: _ignored, ...stateJson } = state as DesktopPersistentState & { version?: number }
  const body: Record<string, unknown> = { state_json: stateJson }
  if (expected !== undefined) body.expected_version = expected
  keepaliveFetch('/desktop/state', body)
}

export const desktopStateStore = { state, loaded }
