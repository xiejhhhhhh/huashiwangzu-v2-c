import { getApiUrl, authHeaders, handleUnauthorized, apiPost as runtimeApiPost } from '../runtime'

export const apiPost = runtimeApiPost

export async function downloadBlob(fileId: number): Promise<Blob> {
  const url = getApiUrl(`/files/download/${fileId}`)
  const resp = await fetch(url, { headers: authHeaders() })
  if (handleUnauthorized(resp.status)) throw new Error('登录已失效，请重新登录')
  if (!resp.ok) throw new Error(`Download returned ${resp.status}`)
  return resp.blob()
}
