import { apiGet } from '../runtime'

export async function checkHealth(): Promise<{ libreoffice: boolean }> {
  return apiGet('/office-gen/health')
}
