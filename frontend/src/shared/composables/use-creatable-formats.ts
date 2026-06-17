import { computed } from 'vue'
import { getAppRegistry } from '@/desktop/app-registry/desktop-app-state'

interface CreatableFormat {
  extension: string
  label: string
  mime_type?: string
}

export function useCreatableFormats() {
  const formats = computed<CreatableFormat[]>(() => {
    const seen = new Set<string>()
    const result: CreatableFormat[] = []
    for (const app of Object.values(getAppRegistry())) {
      if (!app.creatableFormats) continue
      for (const fmt of app.creatableFormats) {
        if (seen.has(fmt.extension)) continue
        seen.add(fmt.extension)
        result.push(fmt)
      }
    }
    return result
  })

  return { creatableFormats: formats }
}
