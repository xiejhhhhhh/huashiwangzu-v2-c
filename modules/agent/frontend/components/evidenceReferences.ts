export interface EvidenceReference {
  type: string
  ref_key: string
  ref_id: string
  title?: string
  source?: string
  source_tool?: string
  status?: string
  excerpt?: string
}

export interface EvidenceReferenceContext {
  sourceTool?: string | null
  status?: string | null
  fallbackRefKey?: string
  fallbackType?: string
}

export const EVIDENCE_REF_LABELS: Record<string, string> = {
  file_id: '文件',
  source_file_id: '源文件',
  package_id: '内容包',
  artifact_id: '产物',
  document_id: '文档',
  chunk_id: '片段',
  page: '页码',
}

const KNOWN_REF_KEYS = new Set(Object.keys(EVIDENCE_REF_LABELS))

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function scalarToString(value: unknown): string | null {
  if (typeof value === 'string') {
    const trimmed = value.trim()
    return trimmed || null
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  return null
}

function stringField(record: Record<string, unknown>, key: string): string | undefined {
  const value = record[key]
  return typeof value === 'string' && value.trim() ? value.trim() : undefined
}

function refTypeFromKey(refKey: string): string {
  return refKey.endsWith('_id') ? refKey.slice(0, -3).replace(/_/g, '-') : refKey.replace(/_/g, '-')
}

function withContext(ref: EvidenceReference, context: EvidenceReferenceContext): EvidenceReference {
  return {
    ...ref,
    source_tool: ref.source_tool || context.sourceTool || undefined,
    status: ref.status || context.status || undefined,
  }
}

function directReferenceFromRecord(record: Record<string, unknown>, context: EvidenceReferenceContext): EvidenceReference | null {
  const refKey = stringField(record, 'ref_key') || stringField(record, 'refKey') || context.fallbackRefKey
  if (!refKey) return null
  const refId = scalarToString(record.ref_id) || scalarToString(record.refId) || scalarToString(record[refKey])
  if (!refId) return null
  return withContext({
    type: stringField(record, 'type') || context.fallbackType || refTypeFromKey(refKey),
    ref_key: refKey,
    ref_id: refId,
    title: stringField(record, 'title'),
    source: stringField(record, 'source'),
    source_tool: stringField(record, 'source_tool') || stringField(record, 'sourceTool'),
    status: stringField(record, 'status'),
    excerpt: stringField(record, 'excerpt'),
  }, context)
}

function dedupeReferences(refs: EvidenceReference[]): EvidenceReference[] {
  const seen = new Set<string>()
  const result: EvidenceReference[] = []
  for (const ref of refs) {
    const key = [ref.type, ref.ref_key, ref.ref_id, ref.source_tool || '', ref.status || ''].join(':')
    if (seen.has(key)) continue
    seen.add(key)
    result.push(ref)
  }
  return result
}

export function collectEvidenceReferences(
  value: unknown,
  context: EvidenceReferenceContext = {},
  depth = 0,
): EvidenceReference[] {
  if (depth > 6) return []
  const primitiveId = scalarToString(value)
  if (primitiveId && context.fallbackRefKey) {
    return [withContext({
      type: context.fallbackType || refTypeFromKey(context.fallbackRefKey),
      ref_key: context.fallbackRefKey,
      ref_id: primitiveId,
    }, context)]
  }
  if (Array.isArray(value)) {
    return dedupeReferences(value.flatMap(item => collectEvidenceReferences(item, context, depth + 1)))
  }
  if (!isRecord(value)) return []

  const refs: EvidenceReference[] = []
  const directRef = directReferenceFromRecord(value, context)
  if (directRef) refs.push(directRef)
  for (const [key, child] of Object.entries(value)) {
    if (KNOWN_REF_KEYS.has(key)) {
      const refId = scalarToString(child)
      if (refId) {
        refs.push(withContext({
          type: refTypeFromKey(key),
          ref_key: key,
          ref_id: refId,
          title: `${EVIDENCE_REF_LABELS[key]} ${refId}`,
          source: key,
        }, context))
      }
    }
    refs.push(...collectEvidenceReferences(child, context, depth + 1))
  }
  return dedupeReferences(refs)
}

export function evidenceReferencesFromIds(
  refKey: string,
  ids: unknown[] | undefined,
  context: EvidenceReferenceContext = {},
): EvidenceReference[] {
  if (!ids?.length) return []
  return collectEvidenceReferences(ids, {
    ...context,
    fallbackRefKey: refKey,
    fallbackType: context.fallbackType || refTypeFromKey(refKey),
  })
}

export function evidenceReferenceKey(ref: EvidenceReference, index: number): string {
  return `${ref.ref_key}:${ref.ref_id}:${ref.source_tool || ''}:${ref.status || ''}:${index}`
}

export function evidenceReferenceLabel(ref: EvidenceReference): string {
  return EVIDENCE_REF_LABELS[ref.ref_key] || ref.type || ref.ref_key
}

export function evidenceReferenceOpenReason(ref: EvidenceReference): string {
  if (ref.ref_key === 'file_id' || ref.ref_key === 'source_file_id') {
    return numericFileId(ref) === null ? '文件 id 不是数字，暂不可直接打开' : '可打开文件'
  }
  if (ref.ref_key === 'document_id' || ref.ref_key === 'chunk_id' || ref.ref_key === 'page') {
    return '当前没有直接打开入口，请通过知识库证据/文档页面查看'
  }
  if (ref.ref_key === 'package_id' || ref.ref_key === 'artifact_id') {
    return '当前没有直接打开入口，请通过产物或内容包页面查看'
  }
  return '当前没有直接打开入口'
}

export function canOpenEvidenceReference(ref: EvidenceReference): boolean {
  return (ref.ref_key === 'file_id' || ref.ref_key === 'source_file_id') && numericFileId(ref) !== null
}

export function numericFileId(ref: EvidenceReference): number | null {
  const fileId = Number(ref.ref_id)
  return Number.isInteger(fileId) && fileId > 0 ? fileId : null
}
