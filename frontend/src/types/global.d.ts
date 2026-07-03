/**
 * Global window extensions shared across modules.
 * Declared here so all modules can access these properties
 * without unsafe window casts.
 */

export {}

declare global {
  interface Window {
    /** Framework runtime config injected at page load */
    __HSWZ_CONFIG__?: { api_base_url?: string }

    /** Desktop platform bridge injected by the shell */
    platform?: {
      modules?: {
        openApp?: (appId: string, opts?: Record<string, unknown>) => void
      }
    }

    /** Desktop event bus exposed for framework-integrated modules */
    __DESKTOP_EVENT_BUS__?: {
      emit: (name: string, payload: Record<string, unknown>) => void
    }
  }
}

declare module 'element-plus/dist/locale/zh-cn.mjs' {
  const zhCn: unknown
  export default zhCn
}
