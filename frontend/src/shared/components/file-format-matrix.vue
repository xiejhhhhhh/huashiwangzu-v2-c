<template>
  <el-table :data="filteredRows" stripe border size="small" style="width: 100%" class="format-matrix-table" :row-class-name="getRowClass">
    <el-table-column prop="format" label="格式" width="85" />
    <el-table-column prop="displayName" label="中文名称" width="115" />
    <el-table-column prop="category" label="分类" width="90" />
    <el-table-column label="可预览" width="78">
      <template #default="{ row }">
        <el-tag :type="row.previewable ? 'success' : 'danger'" size="small" effect="plain" :class="row.previewable ? '' : 'format-incompatible'">
          {{ row.previewable ? '是' : '否' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="showEditableColumn" label="editable" width="78">
      <template #default="{ row }">
        <el-tag :type="row.editable ? 'success' : 'danger'" size="small" effect="plain">
          {{ row.editable ? '是' : '否' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="showEditorColumn" prop="editor" label="编辑器" width="105" />
    <el-table-column label="说明" min-width="160">
      <template #default="{ row }">
        <span :class="['format-hint', getDescriptionClass(row.description)]">{{ row.description }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface FormatRow {
  format: string
  displayName: string
  category: string
  previewable: boolean
  editable: boolean
  editor: string
  description: string
}

const props = withDefaults(defineProps<{
  filterRole?: string
  compact?: boolean
}>(), {
  filterRole: '',
  compact: false,
})

const incompatibleFormats = ['doc', 'xls', 'ppt', 'vsd', 'vsdx', 'mpp', 'zip', 'rar']

function getRowClass({ row }: { row: FormatRow }) {
  return incompatibleFormats.includes(row.format) ? 'format-support-row format-incompatible-row' : 'format-support-row'
}

const displayNames: Record<string, string> = {
  txt: '纯文本', md: 'Markdown 文档', log: '日志文件', json: 'JSON 数据',
  xml: 'XML 文档', yaml: 'YAML 配置', yml: 'YAML 配置', php: 'PHP 脚本',
  js: 'JavaScript 脚本', ts: 'TypeScript 脚本', vue: 'Vue 组件', css: 'CSS 样式',
  html: 'HTML 网页', py: 'Python 脚本', java: 'Java 代码', go: 'Go 代码',
  rs: 'Rust 代码', kt: 'Kotlin 代码', c: 'C 源码', cpp: 'C++ 源码',
  h: 'C 头文件', hpp: 'C++ 头文件', cs: 'C# 代码', rb: 'Ruby 脚本',
  sh: 'Shell 脚本', bash: 'Bash 脚本', zsh: 'Zsh 脚本',
  ini: 'INI 配置', cfg: '配置文件', conf: '配置文件', env: '环境变量文件',
  sql: 'SQL 查询', toml: 'TOML 配置', dockerfile: 'Dockerfile 构建', makefile: 'Makefile 构建',
  csv: 'CSV 表格', png: 'PNG 图片', jpg: 'JPEG 图片', jpeg: 'JPEG 图片',
  gif: 'GIF 图片', webp: 'WebP 图片', bmp: 'BMP 图片', ico: 'ICO 图标',
  svg: 'SVG 矢量图', pdf: 'PDF 文档', mp3: 'MP3 音频', wav: 'WAV 音频',
  aac: 'AAC 音频', ogg: 'OGG 音频', flac: 'FLAC 音频', m4a: 'M4A 音频',
  mp4: 'MP4 视频', webm: 'WebM 视频', mov: 'MOV 视频', m4v: 'M4V 视频',
  xlsx: 'Excel 工作簿', docx: 'Word 文档', pptx: 'PPT 演示',
  doc: '旧版 Word', xls: '旧版 Excel', ppt: '旧版 PPT',
  vsd: 'Visio 绘图', vsdx: 'Visio 绘图', mpp: 'Project 文件',
  zip: 'ZIP 压缩包', rar: 'RAR 压缩包',
}

const showEditableColumn = computed(() => props.filterRole !== 'viewer' && !props.compact)
const showEditorColumn = computed(() => !props.compact)

function buildRows(formatGroup: string[], attrs: Partial<FormatRow>): FormatRow[] {
  return formatGroup.map(format => ({
    format,
    displayName: displayNames[format] || format.toUpperCase(),
    category: attrs.category || '',
    previewable: attrs.previewable || false,
    editable: attrs.editable || false,
    editor: attrs.editor || '—',
    description: attrs.description || '',
  }))
}

const allRows: FormatRow[] = [
  ...buildRows(['txt','md','log','json','xml','yaml','yml','php','js','ts','vue','css','html','py','java','go','rs','kt','c','cpp','h','hpp','cs','rb','sh','bash','zsh','ini','cfg','conf','env','sql','toml','dockerfile','makefile'], { category: '文本/代码', previewable: false, editable: true, editor: 'textEditor', description: '直接编辑' }),
  ...buildRows(['csv'], { category: '表格', previewable: false, editable: true, editor: 'csvEditor', description: '直接编辑' }),
  ...buildRows(['png','jpg','jpeg','gif','webp','bmp','ico','svg'], { category: '图片', previewable: true, editable: false, description: '只读预览' }),
  ...buildRows(['pdf'], { category: 'PDF', previewable: true, editable: false, description: '只读预览' }),
  ...buildRows(['mp3','wav','aac','ogg','flac','m4a'], { category: '音频', previewable: true, editable: false, description: '只读预览' }),
  ...buildRows(['mp4','webm','mov','m4v'], { category: '视频', previewable: true, editable: false, description: '只读预览' }),
  ...buildRows(['xlsx'], { category: '表格', previewable: false, editable: true, editor: 'excelEditor', description: '需创建JSON包' }),
  ...buildRows(['docx'], { category: '文档', previewable: false, editable: true, editor: 'docxEditor', description: '需创建JSON包' }),
  ...buildRows(['pptx'], { category: '演示', previewable: false, editable: true, editor: 'pptxEditor', description: '需创建JSON包' }),
  ...buildRows(['doc','xls','ppt'], { category: '旧格式', previewable: true, editable: false, description: '不支持在线编辑，请下载' }),
  ...buildRows(['vsd','vsdx','mpp','zip','rar'], { category: '其他', previewable: true, editable: false, description: '不支持在线预览，请下载' }),
]

const filteredRows = computed(() => {
  if (!props.filterRole) return allRows
  const role = props.filterRole.toLowerCase()
  if (role === 'viewer') {
    return allRows.map(row => ({ ...row, editable: false }))
  }
  return allRows
})

function getDescriptionClass(description: string): string {
  if (description.includes('不支持')) return 'text-unsupported'
  if (description.includes('需创建') || description.includes('只读')) return 'text-limited'
  return 'text-supported'
}
</script>

<style scoped>
.text-supported { color: var(--el-color-success); font-weight: 500; }
.text-limited { color: var(--el-color-warning); font-weight: 500; }
.text-unsupported { color: var(--el-color-danger); font-weight: 500; }
</style>
