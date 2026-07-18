/**
 * mac-app-v1 App UI Kit public entry.
 * Business modules/products should import from here — not invent shell chrome.
 */
export { MAC_APP_KIT_ID, toWindowFrameLayout } from './types'
export type {
  MacAppDensity,
  MacAppFeedbackChannel,
  MacAppLayout,
  MacAppSlotMode,
  MacAppUiContract,
} from './types'

export { useAppFeedback } from './use-app-feedback'
export type { AppFeedback } from './use-app-feedback'

export { default as MacAppShell } from './mac-app-shell.vue'
export { default as MacEmptyState } from './mac-empty-state.vue'

// Re-export existing chrome primitives so apps have one import surface.
export { default as AppWindowFrame } from '@/desktop/components/app-window-frame.vue'
export { default as AppToolbar } from '@/desktop/components/app-toolbar.vue'
export { default as AppStatusBar } from '@/desktop/components/app-status-bar.vue'

import './tokens-app.css'
