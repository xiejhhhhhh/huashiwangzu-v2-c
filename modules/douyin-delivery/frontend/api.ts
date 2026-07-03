import { apiDelete, apiGet, apiPost, apiPut } from '../runtime'

export interface Product {
  id: number
  name: string
  category: string
  selling_points: string[] | null
  ingredients: string[] | null
  target_audience: string
  brand: string
  notes: string
  created_at: string | null
  updated_at: string | null
}

export interface Script {
  id: number
  title: string
  product_id: number | null
  product_name: string
  channel: string
  hook: string
  pain_point: string
  selling_point: string
  social_proof: string
  call_to_action: string
  full_script: string
  style_notes: string
  hashtags: string[] | null
  suggested_titles: string[] | null
  status: string
  version: number
  created_at: string | null
  updated_at: string | null
}

export interface AdCopy {
  id: number
  product_id: number | null
  product_name: string
  channel: string
  ad_type: string
  title: string
  headline: string
  description: string
  call_to_action: string
  target_audience_desc: string
  landing_page_suggestion: string
  status: string
  version: number
  created_at: string | null
  updated_at: string | null
}

export interface Campaign {
  id: number
  name: string
  channel: string
  status: string
  budget: number | null
  budget_type: string
  start_date: string
  end_date: string
  target_audience: Record<string, unknown> | null
  product_ids: number[] | null
  script_ids: number[] | null
  ad_copy_ids: number[] | null
  notes: string
  performance_metrics: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}

export interface DeliveryAccount {
  id: number
  channel: string
  account_name: string
  external_account_id: string
  status: string
  notes: string
  created_at: string | null
  updated_at: string | null
}

export interface DeliveryMaterial {
  id: number
  title: string
  material_type: string
  channel: string
  source_file_id: number | null
  content_url: string
  content_text: string
  status: string
  notes: string
  metadata_json: Record<string, unknown> | null
  created_at: string | null
  updated_at: string | null
}

export interface DeliveryTask {
  id: number
  task_type: string
  target_type: string
  target_id: number | null
  status: string
  priority: number
  payload: Record<string, unknown> | null
  result_payload: Record<string, unknown> | null
  error_message: string
  started_at: string | null
  finished_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface DeliveryTaskCreateRequest extends Partial<DeliveryTask> {
  auto_execute?: boolean
}

export interface GenerateResult {
  script?: string
  ad_copy?: string
  raw: unknown
  channel: string
  channel_label?: string
  ad_type?: string
}

export interface ValidationResult {
  has_knowledge_base_results: boolean
  knowledge_results: unknown[]
  evidence_meta: unknown
  ai_validation: string
}

export interface Prompt {
  id: number
  key: string
  name: string
  content: string
  description: string
  category: string
  channel: string
  created_at: string | null
  updated_at: string | null
}

const BASE = '/api/douyin-delivery'

export const products = {
  list: () => apiGet<Product[]>(`${BASE}/products`),
  create: (data: Partial<Product>) => apiPost<Product>(`${BASE}/products`, data),
  update: (id: number, data: Partial<Product>) => apiPut<Product>(`${BASE}/products/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/products/${id}`),
}

export const scripts = {
  generate: (product: string, channel: string) =>
    apiPost<GenerateResult>(`${BASE}/scripts/generate`, { product, channel }),
  list: (channel?: string) =>
    apiGet<Script[]>(`${BASE}/scripts${channel ? `?channel=${channel}` : ''}`),
  get: (id: number) => apiGet<Script>(`${BASE}/scripts/${id}`),
  create: (data: Partial<Script>) => apiPost<Script>(`${BASE}/scripts`, data),
  update: (id: number, data: Partial<Script>) => apiPut<Script>(`${BASE}/scripts/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/scripts/${id}`),
}

export const adCopies = {
  generate: (product: string, channel: string, adType: string) =>
    apiPost<GenerateResult>(`${BASE}/ad-copies/generate`, { product, channel, ad_type: adType }),
  list: (channel?: string) =>
    apiGet<AdCopy[]>(`${BASE}/ad-copies${channel ? `?channel=${channel}` : ''}`),
  create: (data: Partial<AdCopy>) => apiPost<AdCopy>(`${BASE}/ad-copies`, data),
  update: (id: number, data: Partial<AdCopy>) => apiPut<AdCopy>(`${BASE}/ad-copies/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/ad-copies/${id}`),
}

export const campaigns = {
  list: () => apiGet<Campaign[]>(`${BASE}/campaigns`),
  create: (data: Partial<Campaign>) => apiPost<Campaign>(`${BASE}/campaigns`, data),
  update: (id: number, data: Partial<Campaign>) => apiPut<Campaign>(`${BASE}/campaigns/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/campaigns/${id}`),
  analyze: (id: number) => apiPost<{ campaign: Campaign; analysis: string }>(`${BASE}/campaigns/${id}/analyze`),
}

export const accounts = {
  list: (channel?: string) =>
    apiGet<DeliveryAccount[]>(`${BASE}/accounts${channel ? `?channel=${channel}` : ''}`),
  create: (data: Partial<DeliveryAccount>) => apiPost<DeliveryAccount>(`${BASE}/accounts`, data),
  update: (id: number, data: Partial<DeliveryAccount>) => apiPut<DeliveryAccount>(`${BASE}/accounts/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/accounts/${id}`),
}

export const materials = {
  list: (materialType?: string, status?: string) => {
    const qs = new URLSearchParams()
    if (materialType) qs.set('material_type', materialType)
    if (status) qs.set('status', status)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return apiGet<DeliveryMaterial[]>(`${BASE}/materials${suffix}`)
  },
  create: (data: Partial<DeliveryMaterial>) => apiPost<DeliveryMaterial>(`${BASE}/materials`, data),
  update: (id: number, data: Partial<DeliveryMaterial>) => apiPut<DeliveryMaterial>(`${BASE}/materials/${id}`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/materials/${id}`),
}

export const deliveryTasks = {
  list: (status?: string, taskType?: string) => {
    const qs = new URLSearchParams()
    if (status) qs.set('status', status)
    if (taskType) qs.set('task_type', taskType)
    const suffix = qs.toString() ? `?${qs.toString()}` : ''
    return apiGet<DeliveryTask[]>(`${BASE}/delivery-tasks${suffix}`)
  },
  create: (data: DeliveryTaskCreateRequest) => apiPost<DeliveryTask>(`${BASE}/delivery-tasks`, data),
  update: (id: number, data: Partial<DeliveryTask>) => apiPut<DeliveryTask>(`${BASE}/delivery-tasks/${id}`, data),
  markStatus: (id: number, data: { status: string; error_message?: string; result_payload?: Record<string, unknown> }) =>
    apiPost<DeliveryTask>(`${BASE}/delivery-tasks/${id}/status`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/delivery-tasks/${id}`),
}

export const cleanup = {
  markedData: (marker: string) =>
    apiPost<{ marker: string; deleted: Record<string, number>; total_deleted: number }>(`${BASE}/cleanup`, { marker }),
}

export const validation = {
  validate: (content: string) => apiPost<ValidationResult>(`${BASE}/validate`, { content }),
}

export const prompts = {
  list: (category?: string, channel?: string) =>
    apiGet<Prompt[]>(`${BASE}/prompts?${category ? `category=${category}&` : ''}${channel ? `channel=${channel}` : ''}`),
  save: (data: Partial<Prompt>) => apiPost<Prompt>(`${BASE}/prompts`, data),
  delete: (id: number) => apiDelete<{ deleted: boolean }>(`${BASE}/prompts/${id}`),
}
