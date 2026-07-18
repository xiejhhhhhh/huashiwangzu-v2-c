import { defineComponent, h } from 'vue'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import { fetchDesktopProducts } from '@/shared/api/products'
import type { DesktopProductItem } from '@/shared/api/products'
import { componentKeyMap } from '@/desktop/app-registry/component-key-map'
import { setAppRegistry } from '@/desktop/app-registry/desktop-app-state'
import ComponentRegistrationError from '@/desktop/components/component-registration-error.vue'
import { MAC_APP_KIT_ID, type MacAppUiContract } from '@/desktop/app-kit'

const VALID_LAYOUTS = new Set(['finder', 'document', 'chat', 'settings', 'dashboard', 'utility'])

function missingComponentLoader(
  appKey: string,
  appName: string,
  componentKey: string,
): AppRegistryEntry['entryComponent'] {
  console.error(`[app-registry] Missing component loader for ${appKey || appName}: ${componentKey || '<empty>'}`)
  return () => Promise.resolve({
    default: defineComponent({
      name: 'MissingDesktopAppComponent',
      setup() {
        return () => h(ComponentRegistrationError, { appKey, appName, componentKey })
      },
    }),
  })
}

function resolveComponentLoader(
  entryKey: string,
  appKey: string,
  appName: string,
): AppRegistryEntry['entryComponent'] {
  return componentKeyMap[entryKey] || missingComponentLoader(appKey, appName, entryKey)
}

function extensionsFromAssociations(product: DesktopProductItem): {
  supported: string[]
  editable: string[]
} {
  const supported = new Set<string>()
  const editable = new Set<string>()
  for (const raw of product.fileAssociations || []) {
    const assoc = raw as {
      extensions?: string[]
      modes?: string[]
      readOnlyFormats?: string[]
    }
    const modes = (assoc.modes || ['view']).map(String)
    const readonly = new Set((assoc.readOnlyFormats || []).map(e => String(e).toLowerCase().replace(/^\./, '')))
    for (const extRaw of assoc.extensions || []) {
      const ext = String(extRaw).toLowerCase().replace(/^\./, '')
      if (!ext || ext === '*') continue
      supported.add(ext)
      if (modes.includes('edit') && !readonly.has(ext)) editable.add(ext)
    }
  }
  return { supported: [...supported], editable: [...editable] }
}

/**
 * Dev-time / soft gate: product should declare mac-app-v1 uiContract.
 * Does not block loading (catalog may still open legacy shells), but logs loudly.
 */
export function validateProductUiContract(
  product: DesktopProductItem,
): { ok: boolean; warnings: string[]; contract: MacAppUiContract | null } {
  const warnings: string[] = []
  const pid = product.productId || '<unknown>'
  const raw = product.uiContract as MacAppUiContract | null | undefined
  if (!raw || typeof raw !== 'object') {
    warnings.push(`[uiContract] product "${pid}" missing uiContract.kit=mac-app-v1`)
    return { ok: false, warnings, contract: null }
  }
  if (raw.kit !== MAC_APP_KIT_ID) {
    warnings.push(`[uiContract] product "${pid}" kit="${String(raw.kit)}" expected "${MAC_APP_KIT_ID}"`)
  }
  if (!VALID_LAYOUTS.has(String(raw.layout || ''))) {
    warnings.push(`[uiContract] product "${pid}" invalid layout="${String(raw.layout)}"`)
  }
  if (raw.feedback && raw.feedback !== 'desktop-kit') {
    warnings.push(`[uiContract] product "${pid}" feedback="${String(raw.feedback)}" expected "desktop-kit"`)
  }
  return { ok: warnings.length === 0, warnings, contract: raw }
}

function transformProductToEntry(product: DesktopProductItem, aliasOf?: string): AppRegistryEntry {
  const entryKey = product.entryComponentKey || ''
  const windowPolicy = product.windowPolicy || {}
  const visibility = product.visibility || {}
  const appKey = aliasOf || product.productId
  const appName = product.displayName || product.productId
  const { supported, editable } = extensionsFromAssociations(product)
  const creatable = (product.createDocumentTypes || []).map((item) => {
    const row = item as { extension?: string; label?: string; mime_type?: string; mimeType?: string }
    return {
      extension: String(row.extension || ''),
      label: String(row.label || row.extension || ''),
      mime_type: row.mime_type || row.mimeType,
    }
  }).filter(item => item.extension)

  // 主 product 上桌面/启动器；legacyAppKeys 只做 openAppById 别名，不占图标
  const isAlias = Boolean(aliasOf)
  const showDesktop = isAlias ? false : visibility.desktop !== false
  const showLauncher = isAlias ? false : (visibility.launcher !== false || visibility.dock !== false)

  const uiCheck = validateProductUiContract(product)
  if (!isAlias && uiCheck.warnings.length) {
    for (const msg of uiCheck.warnings) {
      console.warn(msg)
    }
  }

  return {
    appKey,
    canonicalAppKey: product.productId,
    appName,
    icon: product.icon || 'Collection',
    description: product.description || '',
    entryComponent: resolveComponentLoader(entryKey, appKey, appName),
    defaultWidth: product.defaultWidth || Number(windowPolicy.defaultWidth) || 900,
    defaultHeight: product.defaultHeight || Number(windowPolicy.defaultHeight) || 640,
    minWidth: Number(windowPolicy.minWidth) || 480,
    minHeight: Number(windowPolicy.minHeight) || 320,
    resizable: true,
    maximizable: true,
    singleton: product.singleton ?? Boolean(windowPolicy.singleton ?? true),
    showOnDesktop: showDesktop,
    showInTray: false,
    showInLauncher: showLauncher,
    showInSidebar: false,
    category: product.category || '',
    supportedFormats: supported.length ? supported : undefined,
    editableFormats: editable.length ? editable : undefined,
    creatableFormats: creatable.length ? creatable : undefined,
    sortOrder: product.sortOrder ?? Number(windowPolicy.sortOrder) ?? 100,
    windowType: 'normal',
    allowMultiple: product.allowMultiple ?? Boolean(windowPolicy.allowMultiple ?? false),
    enabled: product.enabled ?? true,
    uiContract: uiCheck.contract,
  }
}

/**
 * 正式桌面注册表：只加载 Product Catalog。
 * 不再合并 /api/desktop/apps。
 */
export async function loadAppRegistry(_role: string): Promise<AppRegistryEntry[]> {
  const catalog = await fetchDesktopProducts()
  if (!catalog?.items?.length) {
    throw new Error('Product Catalog 为空，无法加载桌面')
  }

  const entries: AppRegistryEntry[] = []
  const claimed = new Set<string>()
  let missingUiContract = 0

  for (const product of catalog.items) {
    const check = validateProductUiContract(product)
    if (!check.ok) missingUiContract += 1
    const main = transformProductToEntry(product)
    entries.push(main)
    claimed.add(main.appKey)

    for (const legacy of product.legacyAppKeys || []) {
      const key = String(legacy || '')
      if (!key || claimed.has(key)) continue
      // 别名：旧调用 openApp('agent') 仍能开到 ai 产品，但不显示第二图标
      entries.push(transformProductToEntry(product, key))
      claimed.add(key)
    }
  }

  if (missingUiContract > 0 && import.meta.env.DEV) {
    console.warn(
      `[app-registry] ${missingUiContract}/${catalog.items.length} products missing valid uiContract.kit=${MAC_APP_KIT_ID}`,
    )
  }

  setAppRegistry(entries)
  return entries
}
