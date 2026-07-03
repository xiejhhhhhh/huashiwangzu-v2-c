import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'

export interface IDisposable {
  dispose(): void
}

export interface CommandMetadata {
  id: string
  title: string
  description?: string
  icon?: string
  category?: string
}

export interface CommandEntry {
  id: string
  title: string
  description?: string
  icon?: string
  category?: string
  handler: (params?: Record<string, unknown>) => unknown | Promise<unknown>
  source?: string
}

export interface SearchResultItem {
  id: string
  type: 'app' | 'command' | 'action' | 'file'
  title: string
  description?: string
  icon?: string
  category?: string
  matchField: 'id' | 'title' | 'description'
  execute: () => unknown | Promise<unknown>
}

type Listener = (id: string) => void

let openAppFn: ((appKey: string) => void) | null = null
let executeActionFn: ((appKey: string, action: string, params?: Record<string, unknown>) => unknown) | null = null

const appOpener = {
  setOpenApp(fn: (appKey: string) => void) { openAppFn = fn },
  setExecuteAction(fn: (appKey: string, action: string, params?: Record<string, unknown>) => unknown) { executeActionFn = fn },
  openApp(appKey: string) { openAppFn?.(appKey) },
  executeAction(appKey: string, action: string, params?: Record<string, unknown>) { return executeActionFn?.(appKey, action, params) },
}

function getSearchResultType(id: string): SearchResultItem['type'] {
  if (!id.startsWith('app:')) return 'command'
  return id.split(':').length > 2 ? 'action' : 'app'
}

class CommandRegistry {
  private _commands = new Map<string, CommandEntry[]>()
  private _listeners = new Set<Listener>()

  register(
    meta: CommandMetadata,
    handler: (params?: Record<string, unknown>) => unknown | Promise<unknown>,
    source?: string,
  ): IDisposable {
    const entry: CommandEntry = {
      id: meta.id,
      title: meta.title,
      description: meta.description,
      icon: meta.icon,
      category: meta.category,
      handler,
      source,
    }
    const existing = this._commands.get(meta.id)
    if (existing) {
      existing.unshift(entry)
    } else {
      this._commands.set(meta.id, [entry])
    }
    this._notify(meta.id)
    return { dispose: () => this._unregister(meta.id, entry) }
  }

  private _unregister(id: string, entry: CommandEntry): void {
    const list = this._commands.get(id)
    if (!list) return
    const idx = list.indexOf(entry)
    if (idx !== -1) list.splice(idx, 1)
    if (list.length === 0) this._commands.delete(id)
    this._notify(id)
  }

  getCommand(id: string): CommandEntry | undefined {
    return this._commands.get(id)?.[0]
  }

  execute(id: string, params?: Record<string, unknown>): unknown | Promise<unknown> {
    const entry = this._commands.get(id)?.[0]
    if (!entry) {
      console.warn(`[CommandRegistry] Command not found: ${id}`)
      return undefined
    }
    return entry.handler(params)
  }

  search(keyword: string): SearchResultItem[] {
    const q = keyword.trim().toLowerCase()
    if (!q) return []

    const results: SearchResultItem[] = []
    const seen = new Set<string>()

    for (const [, entries] of this._commands) {
      for (const entry of entries) {
        const idLow = entry.id.toLowerCase()
        const titleLow = entry.title.toLowerCase()
        const descLow = (entry.description || '').toLowerCase()

        if (idLow === q || titleLow === q) {
          if (seen.has(entry.id)) continue
          seen.add(entry.id)
          results.push({
            id: entry.id,
            type: getSearchResultType(entry.id),
            title: entry.title,
            description: entry.description,
            icon: entry.icon,
            category: entry.category,
            matchField: idLow === q ? 'id' : 'title',
            execute: () => entry.handler(),
          })
          continue
        }

        if (idLow.includes(q) || titleLow.includes(q) || descLow.includes(q)) {
          if (seen.has(entry.id)) continue
          seen.add(entry.id)
          results.push({
            id: entry.id,
            type: getSearchResultType(entry.id),
            title: entry.title,
            description: entry.description,
            icon: entry.icon,
            category: entry.category,
            matchField: idLow.includes(q) ? 'id' : titleLow.includes(q) ? 'title' : 'description',
            execute: () => entry.handler(),
          })
        }
      }
    }

    return results
  }

  onDidRegister(listener: Listener): IDisposable {
    this._listeners.add(listener)
    return {
      dispose: () => this._listeners.delete(listener),
    }
  }

  private _notify(id: string): void {
    for (const fn of this._listeners) {
      try { fn(id) } catch { }
    }
  }

  getAllCommands(): CommandEntry[] {
    const result: CommandEntry[] = []
    for (const [, entries] of this._commands) {
      if (entries.length > 0) result.push(entries[0])
    }
    return result
  }

  registerAppEntry(app: AppRegistryEntry): IDisposable[] {
    const disposables: IDisposable[] = []

    const appDisp = this.register(
      { id: `app:${app.appKey}`, title: app.appName, description: app.description, icon: app.icon, category: app.category || '应用' },
      () => {
        const { openApp } = getAppOpener()
        openApp(app.appKey)
      },
      `app-registry:${app.appKey}`,
    )
    disposables.push(appDisp)

    if (app.publicActions) {
      for (const action of app.publicActions) {
        const actionId = `app:${app.appKey}:${action.action}`
        const actionDisp = this.register(
          { id: actionId, title: `${app.appName} - ${action.description}`, description: action.description, icon: app.icon, category: app.category || '应用' },
          (params) => {
            const { executeAction } = getAppOpener()
            return executeAction(app.appKey, action.action, params)
          },
          `app-registry:${app.appKey}`,
        )
        disposables.push(actionDisp)
      }
    }

    return disposables
  }
}

function getAppOpener() {
  return appOpener
}

export const commandRegistry = new CommandRegistry()
export { getAppOpener }
