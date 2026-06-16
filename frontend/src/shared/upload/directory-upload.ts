import { 获取文件夹树请求, 新建文件夹请求, 上传文件请求 } from '@/shared/api/desktop'

interface 待上传文件 { 文件: File; 路径: string[] }

function 读目录(reader: FileSystemDirectoryReader): Promise<FileSystemEntry[]> {
  return new Promise(resolve => reader.readEntries(resolve))
}

async function 展开条目(entry: FileSystemEntry, 路径: string[] = []): Promise<待上传文件[]> {
  if (entry.isFile) {
    return new Promise(resolve => (entry as FileSystemFileEntry).file(文件 => resolve([{ 文件, 路径 }])))
  }
  const reader = (entry as FileSystemDirectoryEntry).createReader()
  const 当前路径 = [...路径, entry.name]
  const 结果: 待上传文件[] = []
  while (true) {
    const 批次 = await 读目录(reader)
    if (!批次.length) break
    for (const 子项 of 批次) 结果.push(...await 展开条目(子项, 当前路径))
  }
  return 结果
}

export async function 收集拖放文件(items: DataTransferItemList | null): Promise<待上传文件[]> {
  if (!items) return []
  const 结果: 待上传文件[] = []
  for (let i = 0; i < items.length; i++) {
    const entry = items[i].webkitGetAsEntry?.()
    if (entry) 结果.push(...await 展开条目(entry))
    else {
      const 文件 = items[i].getAsFile?.()
      if (文件) 结果.push({ 文件, 路径: [] })
    }
  }
  return 结果
}

export async function 上传拖放文件(文件列表: 待上传文件[], 根文件夹id?: number | null) {
  const 树响应 = await 获取文件夹树请求()
  const 索引 = new Map<string, number>()
  if (树响应.success && 树响应.data) {
    for (const 项 of 树响应.data) 索引.set(`${项.父文件夹id ?? 0}/${项.名称}`, 项.id)
  }

  async function 确保目录(路径: string[]) {
    let 父id = 根文件夹id ?? 0
    for (const 名称 of 路径) {
      const 键 = `${父id}/${名称}`
      if (!索引.has(键)) {
        const res = await 新建文件夹请求(名称, 父id || null)
        索引.set(键, (res.data as any)?.id ?? 0)
      }
      父id = 索引.get(键)!
    }
    return 父id || undefined
  }

  let 成功数 = 0
  let 失败数 = 0
  for (const 项 of 文件列表) {
    try {
      const 文件夹id = await 确保目录(项.路径)
      const res = await 上传文件请求(项.文件, 文件夹id)
      if (res.success) 成功数++
      else 失败数++
    } catch {
      失败数++
    }
  }
  return { 成功数, 失败数 }
}
