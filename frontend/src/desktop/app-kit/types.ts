/**
 * mac-app-v1 UI contract types.
 * Backend/products declare layout intent; frontends compose kit components only.
 */
export type MacAppLayout =
  | 'finder'
  | 'document'
  | 'chat'
  | 'settings'
  | 'dashboard'
  | 'utility'

export type MacAppSlotMode = 'required' | 'optional' | 'none'

export type MacAppDensity = 'comfortable' | 'compact'

export type MacAppFeedbackChannel = 'desktop-kit'

/** Mirrors product.json uiContract (forward-compatible). */
export interface MacAppUiContract {
  kit: 'mac-app-v1'
  layout: MacAppLayout
  shell?: {
    useAppWindowFrame?: boolean
    sidebar?: MacAppSlotMode
    toolbar?: MacAppSlotMode
    statusbar?: MacAppSlotMode
  }
  feedback?: MacAppFeedbackChannel
  density?: MacAppDensity
}

export const MAC_APP_KIT_ID = 'mac-app-v1' as const

/** Maps kit layout → existing AppWindowFrame layout prop. */
export function toWindowFrameLayout(
  layout: MacAppLayout,
): 'management' | 'editor' | 'chat' | 'search' | 'file-manager' | 'dashboard' {
  switch (layout) {
    case 'finder':
      return 'file-manager'
    case 'document':
      return 'editor'
    case 'chat':
      return 'chat'
    case 'settings':
      return 'management'
    case 'dashboard':
      return 'dashboard'
    case 'utility':
    default:
      return 'management'
  }
}
