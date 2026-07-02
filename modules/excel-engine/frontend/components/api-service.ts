/**
 * Excel Engine - API Service Layer
 *
 * Handles all backend communication for the Excel editor.
 */
import { apiPost as post, getApiUrl } from '../../runtime'

export interface CellEditRequest {
  state_key: string
  sheet: string
  address: string
  address_list?: string[]
  method: string
  value?: string
  params?: Record<string, unknown>
}

export interface StyleRequest {
  state_key: string
  sheet: string
  address_list: string[]
  method: string
  params?: Record<string, unknown>
}

export interface StateRequest {
  module: string
  method: string
  params?: Record<string, unknown>
  state_key: string
  sheet: string
}

export interface SheetData {
  cells: Record<string, string>
  styles: Record<string, Record<string, unknown>>
  merges: Record<string, { topLeft: string; rows: number; cols: number }>
  col_widths: Record<string, number>
  row_heights: Record<string, number>
  total_rows: number
  total_cols: number
}

export interface OpenResult extends SheetData {
  state_key: string
  all_sheets: string[]
  sheet_set: Record<string, unknown>
}

export interface EditResult {
  state_key?: string
  cells?: Record<string, string>
  styles?: Record<string, Record<string, unknown>>
  merges?: Record<string, { topLeft: string; rows: number; cols: number }>
  history?: HistoryItem[]
  total_rows?: number
  total_cols?: number
}

export interface HistoryItem {
  id: number
  action: string
  description?: string
  cell_addr?: string
  created_at: string
}

export interface ClipboardRequest {
  state_key: string
  sheet: string
  address: string
  address_list: string[]
  method: string
  params: Record<string, unknown>
}

export async function openFile(fileId: number): Promise<OpenResult> {
  return post<OpenResult>('/excel-engine/open', { file_id: fileId })
}

export async function parseFile(fileId: number): Promise<EditResult> {
  return post<EditResult>('/excel-engine/parse', { file_id: fileId })
}

export async function editCell(req: CellEditRequest): Promise<EditResult> {
  return post<EditResult>('/excel-engine/edit', req)
}

export async function editStyle(req: StyleRequest): Promise<EditResult> {
  return post<EditResult>('/excel-engine/style', req)
}

export async function clipboardOp(req: ClipboardRequest): Promise<EditResult> {
  return post<EditResult>('/excel-engine/clipboard', req)
}

export async function tableOp(req: {
  state_key: string
  sheet: string
  address: string
  address_list: string[]
  method: string
  params: Record<string, unknown>
}): Promise<EditResult> {
  return post<EditResult>('/excel-engine/table', req)
}

export async function stateOp(req: StateRequest): Promise<EditResult> {
  return post<EditResult>('/excel-engine/state', req)
}

export async function dispatch(req: {
  module: string
  method: string
  params: Record<string, unknown>
  state_key: string
  sheet: string
}): Promise<EditResult> {
  return post<EditResult>('/excel-engine/dispatch', req)
}

export function getDownloadUrl(stateKey: string): string {
  return getApiUrl(`/excel-engine/download/${stateKey}`)
}
