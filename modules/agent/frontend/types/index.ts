import type { EvidenceReference } from '../components/evidenceReferences'

export interface AgentEntryProps {
  prefill?: { documentId?: number; documentName?: string; question?: string }
}

export interface ConvItem { id: number; title: string; status?: string }
export interface ModelProfile { key: string; name: string; provider: string; model: string }
export interface RefItem { type: string; title: string; source: string; excerpt: string; url?: string }
export interface ApiBody<T> { success: boolean; data: T; error?: string | null }

export interface UsageData {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  work_duration_ms?: number
  work_duration_sec?: number
  [key: string]: unknown
}

export interface MsgItem {
  id: number
  role: string
  content: string
  created_at?: string | null
  eventType?: string
  toolName?: string
  toolResult?: unknown
  toolStatus?: string
  toolError?: string
  toolCallId?: string
  toolReferences?: EvidenceReference[]
  executionMode?: string
  groupIndex?: number
  groupCount?: number
  toolCount?: number
  toolNodes?: MsgItem[]
  tools?: Array<{
    name?: string
    effective_tool_name?: string
    tool_call_id?: string
  }>
  node?: string
  phase?: string
  status?: string
  targetTool?: string
  elapsedMs?: number
  thinking?: string
  references?: RefItem[]
  tool_events?: unknown[]
  timeline?: unknown[]
  usage?: UsageData | null
  collapsed?: boolean
  running?: boolean
  durationMs?: number
  startedAt?: number
  items?: MsgItem[]
  streaming?: boolean
  streamId?: string
  label?: string
  title?: string
  reason?: string
}

export interface SanitizedMessage {
  content: string
  references: RefItem[]
}

export interface DesktopEventWindow extends Window {
  __DESKTOP_EVENT_BUS__?: { emit: (name: string, payload: Record<string, unknown>) => void }
}
