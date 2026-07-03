import { apiGet, apiPost } from '../runtime'

export type OfficeFormat = 'docx' | 'xlsx' | 'pptx' | 'pdf'

export interface GeneratedFile {
  file_id: number
  name: string
  extension: string
  size: number
  mime_type: string
  deduplicated?: boolean
}

export async function checkHealth(): Promise<{ libreoffice: boolean }> {
  return apiGet('/office-gen/health')
}

export async function generateSample(format: OfficeFormat): Promise<GeneratedFile> {
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  const filename = `office-gen-sample-${format}-${stamp}`

  if (format === 'xlsx') {
    return apiPost<GeneratedFile>('/office-gen/xlsx', {
      filename,
      sheets: [{
        name: 'Summary',
        columns: ['item', 'count'],
        rows: [
          ['Alpha', 1],
          ['Beta', 2],
        ],
      }],
    })
  }

  if (format === 'pptx') {
    return apiPost<GeneratedFile>('/office-gen/pptx', {
      filename,
      slides: [{
        title: 'Office Gen Sample',
        bullets: ['Generated through the module HTTP endpoint', 'Saved by the framework file service'],
      }],
    })
  }

  const content = [
    { type: 'heading', text: 'Office Gen Sample', level: 1 },
    { type: 'paragraph', text: 'Generated through the module HTTP endpoint.' },
    { type: 'table', header: ['item', 'count'], rows: [['Alpha', 1], ['Beta', 2]] },
  ]
  return apiPost<GeneratedFile>(`/office-gen/${format}`, { filename, content })
}
