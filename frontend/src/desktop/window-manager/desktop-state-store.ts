import { reactive, ref } from 'vue'
import { API_BASE_URL } from '@/shared/api'
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

export async function loadDesktopState() {
  const response = await readDesktopStateRequest()
  if (response.success && response.data) {
    state.windows = Array.isArray(response.data.windows) ? response.data.windows : []
    state.appState = response.data.appState || {}
    state.iconPositions = response.data.iconPositions || {}
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

export function saveDesktopStateNow() {
  if (!loaded.value) return Promise.resolve()
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = null
  return saveDesktopStateRequest(JSON.parse(JSON.stringify(state))).then(() => undefined)
}

export function saveDesktopStateWithKeepalive() {
  if (!loaded.value) return
  void fetch(`${API_BASE_URL}/desktop/state`, {
    method: 'POST', credentials: 'include', keepalive: true,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ state_json: state }),
  })
}

export const desktopStateStore = { state, loaded }
