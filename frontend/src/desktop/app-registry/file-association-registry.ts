import { getAppRegistry } from '@/desktop/app-registry/desktop-app-state'
import { getAllowedApps } from './app-registry'

export interface FileAssociationResult {
  appKey: string
  editable: boolean
  category: string
  categoryLabel: string
}

const categoryLabelMap: Record<string, string> = {
  image: 'Image', document: 'Document', text: 'Text', table: 'Table',
  code: 'Code', audio: 'Audio', video: 'Video', legacy: 'Legacy format',
  presentation: 'Presentation', unknown: 'Unknown type',
}

const legacyCategoryLabelMap: Record<string, string> = {
  doc: 'Legacy Word', xls: 'Legacy Excel', ppt: 'Legacy PPT',
  vsd: 'Visio', vsdx: 'Visio', mpp: 'Project', zip: 'Archive', rar: 'Archive',
}

const legacyReadonlyExtensions = ['doc', 'xls', 'ppt', 'vsd', 'vsdx', 'mpp', 'zip', 'rar']

/**
 * Find the best app for a given file format.
 *
 * Matching rules:
 * 1. Exclude apps that declare supported_formats: ["*"] (system file entry only, currently just "desktop")
 * 2. Exclude apps with no supportedFormats or empty array
 * 3. Separate matches into editable and supported groups
 * 4. Within each group, sort by sort_order ascending
 * 5. Editable group has priority over supported group
 * 6. If multiple apps match, pick the first by sort_order (current behavior; future: "Open With" menu)
 *
 * @returns FileAssociationResult or null if no app can open this format
 */
export function getAppByFileFormat(format: string, role?: string): FileAssociationResult | null {
  const ext = (format || '').toLowerCase().replace(/^\./, '')
  if (!ext) return null

  const allApps = role ? getAllowedApps(role) : Object.values(getAppRegistry())

  // Filter to matchable apps: must have non-empty supportedFormats, must not include "*"
  const matchableApps = allApps.filter(app => {
    const formats = app.supportedFormats
    if (!formats || formats.length === 0) return false
    if (formats.includes('*')) return false
    return true
  })

  // Separate into editable and supported matches
  interface MatchCandidate {
    app: typeof allApps[number]
    isEditable: boolean
  }

  const editableMatches: MatchCandidate[] = []
  const supportedMatches: MatchCandidate[] = []

  for (const app of matchableApps) {
    const editableFormats = app.editableFormats ?? []
    if (editableFormats.includes(ext)) {
      editableMatches.push({ app, isEditable: true })
    } else if (app.supportedFormats?.includes(ext)) {
      supportedMatches.push({ app, isEditable: false })
    }
  }

  // Sort by sort_order within each group.
  // prefer product runtime keys: non-viewer product shells (office/text/media/files) over legacy *-viewer
  const rank = (appKey: string) => {
    if (appKey === 'office' || appKey === 'text' || appKey === 'media' || appKey === 'files') return -100
    if (appKey.endsWith('-viewer') || appKey === 'docs-open' || appKey === 'excel-engine') return 50
    return 0
  }
  const sortFn = (a: MatchCandidate, b: MatchCandidate) =>
    rank(a.app.appKey) - rank(b.app.appKey)
    || (a.app.sortOrder ?? 0) - (b.app.sortOrder ?? 0)

  editableMatches.sort(sortFn)
  supportedMatches.sort(sortFn)

  // Pick best: editable first, then supported
  const bestMatch = editableMatches[0] ?? supportedMatches[0]
  if (!bestMatch) {
    return null
  }

  const category = inferFormatCategory(ext, bestMatch.app.appKey)
  return {
    appKey: bestMatch.app.appKey,
    editable: bestMatch.isEditable,
    category,
    categoryLabel: categoryLabelMap[category] || ext.toUpperCase(),
  }
}

function inferFormatCategory(ext: string, appKey: string): string {
  if (appKey === 'image-viewer') return 'image'
  if (appKey === 'text-editor') return ['txt', 'md'].includes(ext) ? 'text' : 'code'
  if (appKey === 'pdf-viewer') return 'document'
  if (appKey === 'doc-viewer') return 'document'
  if (appKey === 'ppt-viewer') return 'presentation'
  if (appKey === 'excel-engine') return 'table'
  if (appKey === 'filePreview') {
    if (['mp3', 'wav', 'aac', 'ogg', 'flac', 'm4a'].includes(ext)) return 'audio'
    if (['mp4', 'webm', 'mov', 'm4v'].includes(ext)) return 'video'
  }
  return 'document'
}

export function getFileAppKey(format: string, role?: string): string | null {
  const result = getAppByFileFormat(format, role)
  return result?.appKey ?? null
}

export function getFileCategoryLabel(format: string, role?: string): string {
  return getAppByFileFormat(format, role)?.categoryLabel ?? 'Unknown type'
}

export function isFormatEditable(format: string, role?: string): boolean {
  return getAppByFileFormat(format, role)?.editable ?? false
}
