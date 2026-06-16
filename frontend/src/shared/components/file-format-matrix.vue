<template>
  <el-table :data="过滤后数据" stripe border size="small" style="width: 100%" class="格式支持矩阵表格" :row-class-name="行样式">
    <el-table-column prop="格式" label="格式" width="85" />
    <el-table-column prop="中文名称" label="中文名称" width="115" />
    <el-table-column prop="分类" label="分类" width="90" />
    <el-table-column label="可预览" width="78">
      <template #default="{ row }">
        <el-tag :type="row.可预览 ? 'success' : 'danger'" size="small" effect="plain" :class="row.可预览 ? '' : '格式不兼容'">
          {{ row.可预览 ? '是' : '否' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="显示editable列" label="editable" width="78">
      <template #default="{ row }">
        <el-tag :type="row.editable ? 'success' : 'danger'" size="small" effect="plain">
          {{ row.editable ? '是' : '否' }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column v-if="显示编辑器列" prop="编辑器" label="编辑器" width="105" />
    <el-table-column label="说明" min-width="160">
      <template #default="{ row }">
        <span :class="['格式提示', 说明样式(row.description)]">{{ row.description }}</span>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface 格式条目 {
  格式: string
  中文名称: string
  分类: string
  可预览: boolean
  editable: boolean
  编辑器: string
  说明: string
}

const props = withDefaults(defineProps<{
  filterRole?: string
  compact?: boolean
}>(), {
  filterRole: '',
  compact: false,
})

const 不兼容格式 = ['doc', 'xls', 'ppt', 'vsd', 'vsdx', 'mpp', 'zip', 'rar']

function 行样式({ row }: { row: 格式条目 }) {
  return 不兼容格式.includes(row.格式) ? '格式支持行 格式不兼容行' : '格式支持行'
}

const 中文名: Record<string, string> = {
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

const 显示editable列 = computed(() => props.filterRole !== 'viewer' && !props.compact)
const 显示编辑器列 = computed(() => !props.compact)

function 构建条目(格式组: string[], attr: Partial<格式条目>): 格式条目[] {
  return 格式组.map(f => ({
    格式: f,
    中文名称: 中文名[f] || f.toUpperCase(),
    分类: attr.分类 || '',
    可预览: attr.可预览 || false,
    editable: attr.editable || false,
    编辑器: attr.编辑器 || '—',
    说明: attr.说明 || '',
  }))
}

const 完整数据: 格式条目[] = [
  ...构建条目(['txt','md','log','json','xml','yaml','yml','php','js','ts','vue','css','html','py','java','go','rs','kt','c','cpp','h','hpp','cs','rb','sh','bash','zsh','ini','cfg','conf','env','sql','toml','dockerfile','makefile'], { 分类: '文本/代码', 可预览: false, editable: true, 编辑器: 'textEditor', 说明: '直接编辑' }),
  ...构建条目(['csv'], { 分类: '表格', 可预览: false, editable: true, 编辑器: 'csvEditor', 说明: '直接编辑' }),
  ...构建条目(['png','jpg','jpeg','gif','webp','bmp','ico','svg'], { 分类: '图片', 可预览: true, editable: false, 说明: '只读预览' }),
  ...构建条目(['pdf'], { 分类: 'PDF', 可预览: true, editable: false, 说明: '只读预览' }),
  ...构建条目(['mp3','wav','aac','ogg','flac','m4a'], { 分类: '音频', 可预览: true, editable: false, 说明: '只读预览' }),
  ...构建条目(['mp4','webm','mov','m4v'], { 分类: '视频', 可预览: true, editable: false, 说明: '只读预览' }),
  ...构建条目(['xlsx'], { 分类: '表格', 可预览: false, editable: true, 编辑器: 'excelEditor', 说明: '需创建JSON包' }),
  ...构建条目(['docx'], { 分类: '文档', 可预览: false, editable: true, 编辑器: 'docxEditor', 说明: '需创建JSON包' }),
  ...构建条目(['pptx'], { 分类: '演示', 可预览: false, editable: true, 编辑器: 'pptxEditor', 说明: '需创建JSON包' }),
  ...构建条目(['doc','xls','ppt'], { 分类: '旧格式', 可预览: true, editable: false, 说明: '不支持在线编辑，请下载' }),
  ...构建条目(['vsd','vsdx','mpp','zip','rar'], { 分类: '其他', 可预览: true, editable: false, 说明: '不支持在线预览，请下载' }),
]

const 过滤后数据 = computed(() => {
  if (!props.filterRole) return 完整数据
  const 角色 = props.filterRole.toLowerCase()
  if (角色 === 'viewer') {
    return 完整数据.map(r => ({ ...r, editable: false }))
  }
  return 完整数据
})

function 说明样式(说明: string): string {
  if (说明.includes('不支持')) return '文本-不支持'
  if (说明.includes('需创建') || 说明.includes('只读')) return '文本-受限'
  return '文本-支持'
}
</script>

<style scoped>
.文本-支持 { color: var(--el-color-success); font-weight: 500; }
.文本-受限 { color: var(--el-color-warning); font-weight: 500; }
.文本-不支持 { color: var(--el-color-danger); font-weight: 500; }
</style>
