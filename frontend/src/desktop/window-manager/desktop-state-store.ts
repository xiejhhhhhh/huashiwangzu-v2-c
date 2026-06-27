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

export async function loadDesktopState() {
  try {
    const data = await readDesktopStateRequest()
    state.windows = Array.isArray(data.windows) ? data.windows : []
    state.appState = data.appState || {}
    state.iconPositions = data.iconPositions || {}
  } catch {
    // desktop state load failed, start with defaults
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
    await saveDesktopStateRequest(JSON.parse(JSON.stringify(state)))
  } catch {
    // desktop state save failed silently
  }
}

export function saveDesktopStateWithKeepalive() {
  if (!loaded.value) return
  keepaliveFetch('/desktop/state', { state_json: state })
}

export const desktopStateStore = { state, loaded }
