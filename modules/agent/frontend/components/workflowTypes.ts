export type JsonValue = unknown
export type JsonRecord = Record<string, unknown>

export interface WorkflowSummary {
  id: number
  title: string
  status: string
  terminal_status?: string | null
  verification_status?: string | null
  progress_summary?: string | null
  needs_confirmation?: boolean
  artifact_summary?: JsonValue
  updated_at?: string | null
  developer_summary?: string | null
  queue_task_ids?: JsonValue
  release_gate_verdict?: string | null
  dirty_worktree_state?: JsonValue
  multi_agent_summary?: MultiAgentSummarySource
  step_count?: number
  tool_call_count?: number
  failure_count?: number
  artifact_count?: number
  verification_count?: number
  reference_count?: number
}

export interface WorkflowListPayload {
  items?: WorkflowSummary[]
  total?: number
}

export type WorkflowListResponse = WorkflowSummary[] | WorkflowListPayload

export type MultiAgentSummaryStatus = 'running' | 'completed' | 'failed' | 'blocked'
export type MultiAgentReferenceId = string | number | JsonRecord

export interface MultiAgentSummaryItem {
  id?: MultiAgentReferenceId | null
  agent_id?: MultiAgentReferenceId | null
  step_id?: MultiAgentReferenceId | null
  name?: string | null
  agent_name?: string | null
  title?: string | null
  step_key?: string | null
  status: MultiAgentSummaryStatus | string
  completion_summary?: string | null
  failure_reason?: string | null
  reference_ids?: MultiAgentReferenceId[]
  artifact_ids?: MultiAgentReferenceId[]
  next_action?: string | null
  updated_at?: string | null
}

export interface MultiAgentSummaryPayload {
  items?: MultiAgentSummaryItem[]
  generated_at?: string | null
  source?: string | null
}

export type MultiAgentSummarySource = MultiAgentSummaryItem[] | MultiAgentSummaryPayload
export type MultiAgentSummaryResponse = MultiAgentSummarySource

export interface WorkflowStep {
  id: number
  run_id?: number
  step_key?: string | null
  title?: string | null
  type?: string | null
  status: string
  order_index?: number | null
  retry_count?: number | null
  max_retries?: number | null
  error_class?: string | null
  error_signature?: string | null
  summary?: string | null
  input_ref?: JsonValue
  output_ref?: JsonValue
  started_at?: string | null
  finished_at?: string | null
}

export interface WorkflowToolCall {
  id: number
  run_id?: number
  step_id?: number | null
  tool_name: string
  target_module?: string | null
  action?: string | null
  caller?: string | null
  arguments_hash?: string | null
  side_effect_level?: string | null
  approval_policy?: string | null
  status: string
  idempotency_key?: string | null
  error_class?: string | null
  error_signature?: string | null
  result_ref?: JsonValue
  started_at?: string | null
  finished_at?: string | null
}

export interface WorkflowArtifact {
  id: number
  run_id?: number
  step_id?: number | null
  artifact_type: string
  storage_kind?: string | null
  storage_ref?: JsonValue
  visibility?: string | null
  lifecycle?: string | null
  checksum?: string | null
  summary?: string | null
  created_at?: string | null
}

export interface WorkflowVerification {
  id: number
  run_id?: number
  step_id?: number | null
  verification_type: string
  status: string
  command_or_capability?: string | null
  evidence_ref?: JsonValue
  summary?: string | null
  is_required_for_completion?: boolean
  duration_ms?: number | null
  created_at?: string | null
}

export interface WorkflowFailure {
  id: number
  run_id?: number
  step_id?: number | null
  tool_call_id?: number | null
  failure_type: string
  error_signature?: string | null
  retryable?: boolean
  retry_count?: number | null
  next_action?: string | null
  evidence_ref?: JsonValue
  handoff_note?: string | null
  created_at?: string | null
}

export interface WorkflowDetailPayload extends WorkflowSummary {
  steps?: WorkflowStep[]
  tool_calls?: WorkflowToolCall[]
  artifacts?: WorkflowArtifact[]
  verifications?: WorkflowVerification[]
  failures?: WorkflowFailure[]
  multi_agent_summary?: MultiAgentSummarySource
}

export interface WorkflowGovernanceError {
  run_id?: number | null
  step_id?: number | null
  tool_call_id?: number | null
  failure_type: string
  reason?: string | null
  retryable?: boolean
  retry_count?: number | null
  next_action?: string | null
  created_at?: string | null
}

export interface WorkflowGovernanceSummary {
  total: number
  failed: number
  partial: number
  completed: number
  needs_confirmation: number
  with_artifacts: number
  with_references: number
  average_duration_ms: number
  recent_errors: WorkflowGovernanceError[]
}
