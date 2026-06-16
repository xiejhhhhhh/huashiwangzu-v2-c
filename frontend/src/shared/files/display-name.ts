export function 格式化文件displayName(文件名?: string | null, 格式?: string | null): string {
  const 名称 = String(文件名 || '')
  const 扩展名 = String(格式 || '').replace(/^\./, '')
  if (!名称 || !扩展名) return 名称
  return 名称.toLowerCase().endsWith(`.${扩展名.toLowerCase()}`) ? 名称 : `${名称}.${扩展名}`
}
