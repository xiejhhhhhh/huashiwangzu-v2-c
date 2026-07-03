<template>
  <div class="media-asr-app">
    <!-- ── Mode selector ── -->
    <div class="toolbar">
      <div class="toolbar-row">
        <label class="field-label">模式</label>
        <div class="mode-group">
          <button
            v-for="m in modes"
            :key="m.key"
            :class="['mode-btn', { active: mode === m.key }]"
            @click="mode = m.key"
          >
            {{ m.label }}
          </button>
        </div>
      </div>

      <!-- ── File selection ── -->
      <div class="toolbar-row">
        <label class="field-label">文件</label>
        <div class="file-input-group">
          <input
            v-model.number="fileId"
            type="number"
            class="file-id-input"
            placeholder="输入 file_id"
            min="1"
          />
          <span class="file-sep">或</span>
          <input
            ref="fileInputRef"
            :accept="acceptExtensions"
            type="file"
            class="file-picker"
            hidden
            @change="onFilePicked"
          />
          <button class="upload-btn" @click="triggerFilePicker">
            {{ uploading ? '上传中…' : '选择文件上传' }}
          </button>
          <span v-if="uploadedFileName" class="uploaded-name">{{ uploadedFileName }}</span>
        </div>
      </div>

      <!-- ── Task-specific parameters ── -->
      <template v-if="mode === 'extract_audio'">
        <div class="toolbar-row">
          <label class="field-label">音频格式</label>
          <select v-model="audioFormat" class="param-select">
            <option v-for="f in audioFormats" :key="f" :value="f">{{ f }}</option>
          </select>
          <label class="field-label-offset">采样率</label>
          <select v-model="sampleRate" class="param-select">
            <option v-for="r in sampleRates" :key="r" :value="r">{{ r }} Hz</option>
          </select>
        </div>
        <div class="toolbar-row">
          <label class="field-label">保存音频</label>
          <el-switch v-model="saveFile" />
        </div>
      </template>

      <template v-if="mode === 'transcribe_audio'">
        <div class="toolbar-row">
          <label class="field-label">Whisper 模型</label>
          <select v-model="whisperModel" class="param-select">
            <option v-for="m in whisperModels" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
          <label class="field-label-offset">语言</label>
          <input v-model="language" class="lang-input" placeholder="自动检测留空" />
        </div>
        <div class="toolbar-row">
          <label class="field-label">保存文本</label>
          <el-switch v-model="saveText" />
        </div>
      </template>

      <template v-if="mode === 'transcribe_video'">
        <div class="toolbar-row">
          <label class="field-label">采样率</label>
          <select v-model="sampleRate" class="param-select">
            <option v-for="r in sampleRates" :key="r" :value="r">{{ r }} Hz</option>
          </select>
        </div>
        <div class="toolbar-row">
          <label class="field-label">Whisper 模型</label>
          <select v-model="whisperModel" class="param-select">
            <option v-for="m in whisperModels" :key="m.value" :value="m.value">{{ m.label }}</option>
          </select>
          <label class="field-label-offset">语言</label>
          <input v-model="language" class="lang-input" placeholder="自动检测留空" />
        </div>
        <div class="toolbar-row">
          <label class="field-label">保存音频</label>
          <el-switch v-model="saveAudio" />
          <label class="field-label-offset">保存文本</label>
          <el-switch v-model="saveText" />
        </div>
      </template>

      <!-- ── Execute ── -->
      <div class="toolbar-row">
        <label class="field-label">&nbsp;</label>
        <button class="exec-btn" :disabled="!canExecute" @click="doExecute">
          {{ running ? '处理中…' : labelForMode }}
        </button>
        <span v-if="durationMs !== null" class="duration-info">{{ (durationMs / 1000).toFixed(1) }}s</span>
      </div>
    </div>

    <div v-if="errorMsg" class="error-bar">{{ errorMsg }}</div>

    <!-- ── Result area ── -->
    <div v-if="result" class="result-area">
      <div class="result-summary">
        <span class="result-badge ok">完成</span>
        <span v-if="result.audio_file_id" class="file-id-badge">音频 ID: {{ result.audio_file_id }}</span>
        <span v-if="displayTextFileId" class="file-id-badge">文本 ID: {{ displayTextFileId }}</span>
      </div>

      <div v-if="result.text" class="result-section">
        <div class="section-header">转录全文</div>
        <pre class="transcript-text">{{ result.text }}</pre>
      </div>

      <div v-if="result.segments && result.segments.length" class="result-section">
        <div class="section-header">分段列表（{{ result.segments.length }} 段）</div>
        <table class="segments-table">
          <thead>
            <tr>
              <th class="col-time">开始</th>
              <th class="col-time">结束</th>
              <th>文本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(seg, i) in result.segments" :key="i">
              <td class="col-time">{{ fmtTime(seg.start) }}</td>
              <td class="col-time">{{ fmtTime(seg.end) }}</td>
              <td>{{ seg.text }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-if="result.source_file_id" class="result-section meta-section">
        源文件 ID: {{ result.source_file_id }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { initRuntime, platform, files } from '../runtime'

interface TranscribeSegment {
  start: number
  end: number
  text: string
}

interface TranscribeResult {
  source_file_id?: number
  file_id?: number
  audio_file_id?: number
  text_file_id?: number
  text?: string
  segments?: TranscribeSegment[]
  format?: string
  model?: string
  audio_format?: string
  sample_rate?: number
  duration_seconds?: number
  size?: number
  metadata?: {
    segment_count?: number
    sample_rate?: number
    text_file_id?: number | null
  }
  error?: string
  detail?: string
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isTranscribeSegment(value: unknown): value is TranscribeSegment {
  if (!isRecord(value)) return false
  return typeof value.start === 'number' && typeof value.end === 'number' && typeof value.text === 'string'
}

function isOptionalNumber(value: unknown): boolean {
  return value === undefined || typeof value === 'number'
}

function isOptionalString(value: unknown): boolean {
  return value === undefined || typeof value === 'string'
}

function isOptionalNullableNumber(value: unknown): boolean {
  return value === undefined || value === null || typeof value === 'number'
}

function isTranscribeMetadata(value: unknown): value is TranscribeResult['metadata'] {
  if (value === undefined) return true
  if (!isRecord(value)) return false
  return (
    isOptionalNumber(value.segment_count) &&
    isOptionalNumber(value.sample_rate) &&
    isOptionalNullableNumber(value.text_file_id)
  )
}

function isTranscribeResult(value: unknown): value is TranscribeResult {
  if (!isRecord(value)) return false
  if (!isOptionalNumber(value.source_file_id)) return false
  if (!isOptionalNumber(value.file_id)) return false
  if (!isOptionalNumber(value.audio_file_id)) return false
  if (!isOptionalNumber(value.text_file_id)) return false
  if (!isOptionalString(value.text)) return false
  if (!isOptionalString(value.format)) return false
  if (!isOptionalString(value.model)) return false
  if (!isOptionalString(value.audio_format)) return false
  if (!isOptionalNumber(value.sample_rate)) return false
  if (!isOptionalNumber(value.duration_seconds)) return false
  if (!isOptionalNumber(value.size)) return false
  if (!isTranscribeMetadata(value.metadata)) return false
  if (!isOptionalString(value.error)) return false
  if (!isOptionalString(value.detail)) return false
  if (value.segments !== undefined) {
    return Array.isArray(value.segments) && value.segments.every(isTranscribeSegment)
  }
  return true
}

const modes = [
  { key: 'transcribe_video', label: '视频转文字' },
  { key: 'extract_audio', label: '仅提取音频' },
  { key: 'transcribe_audio', label: '音频转文字' },
] as const

const audioFormats = ['wav', 'mp3', 'm4a', 'flac', 'ogg']
const sampleRates = [8000, 16000, 22050, 24000, 32000, 44100, 48000]
const whisperModels = [
  { value: 'large-v3', label: 'large-v3（推荐）' },
  { value: 'large-v2', label: 'large-v2' },
  { value: 'medium', label: 'medium' },
  { value: 'small', label: 'small' },
  { value: 'tiny', label: 'tiny' },
  { value: 'turbo', label: 'turbo' },
]

const mode = ref<'transcribe_video' | 'extract_audio' | 'transcribe_audio'>('transcribe_video')
const fileId = ref<number | undefined>(undefined)
const uploadedFileName = ref('')
const uploading = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// extract_audio / transcribe_video params
const audioFormat = ref('wav')
const sampleRate = ref(16000)
const saveFile = ref(true)
const saveAudio = ref(true)

// transcribe_audio / transcribe_video params
const whisperModel = ref('large-v3')
const language = ref('')
const saveText = ref(true)

const running = ref(false)
const errorMsg = ref('')
const result = ref<TranscribeResult | null>(null)
const durationMs = ref<number | null>(null)
const displayTextFileId = computed(() => result.value?.text_file_id ?? result.value?.metadata?.text_file_id ?? null)

const acceptExtensions = computed(() => {
  if (mode.value === 'extract_audio' || mode.value === 'transcribe_video') {
    return '.mp4,.mov,.m4v,.webm,.mkv,.avi'
  }
  return '.wav,.mp3,.m4a,.aac,.flac,.ogg'
})

const labelForMode = computed(() => {
  const map: Record<string, string> = {
    transcribe_video: '提取并转录',
    extract_audio: '提取音频',
    transcribe_audio: '转录文字',
  }
  return map[mode.value] || '执行'
})

const canExecute = computed(() => {
  if (running.value) return false
  if (mode.value === 'extract_audio' || mode.value === 'transcribe_video') {
    return fileId.value !== undefined && fileId.value > 0
  }
  return fileId.value !== undefined && fileId.value > 0
})

onMounted(async () => {
  await initRuntime('media-asr')
})

function triggerFilePicker(): void {
  fileInputRef.value?.click()
}

async function onFilePicked(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  if (!input.files || !input.files[0]) return
  uploading.value = true
  errorMsg.value = ''
  try {
    const file = input.files[0]
    uploadedFileName.value = file.name
    const uploadResult = await files.upload(file)
    fileId.value = uploadResult.id
  } catch (err: unknown) {
    errorMsg.value = err instanceof Error ? err.message : '上传失败'
  } finally {
    uploading.value = false
    if (input) input.value = ''
  }
}

function fmtTime(seconds: number): string {
  const m = Math.floor(seconds / 60)
  const s = (seconds % 60).toFixed(1)
  return m > 0 ? `${m}:${s.padStart(4, '0')}` : `${s}s`
}

function buildParams(): Record<string, unknown> {
  const base: Record<string, unknown> = { file_id: fileId.value! }
  if (mode.value === 'extract_audio') {
    base.sample_rate = sampleRate.value
    base.audio_format = audioFormat.value
    base.save_file = saveFile.value
  } else if (mode.value === 'transcribe_audio') {
    base.model = whisperModel.value
    base.language = language.value || null
    base.save_text = saveText.value
  } else {
    base.model = whisperModel.value
    base.sample_rate = sampleRate.value
    base.language = language.value || null
    base.save_audio = saveAudio.value
    base.save_text = saveText.value
  }
  return base
}

async function doExecute(): Promise<void> {
  if (running.value) return
  if (!fileId.value || fileId.value <= 0) {
    errorMsg.value = '请先选择文件'
    return
  }

  running.value = true
  errorMsg.value = ''
  result.value = null
  durationMs.value = null
  const t0 = performance.now()

  try {
    const resp = await platform.modules.call('media-asr', mode.value, buildParams())
    if (!isTranscribeResult(resp)) {
      throw new Error('返回格式不正确')
    }
    if (resp.error) {
      errorMsg.value = resp.error
      return
    }
    result.value = resp
  } catch (err: unknown) {
    errorMsg.value = err instanceof Error ? err.message : '调用失败'
  } finally {
    running.value = false
    durationMs.value = performance.now() - t0
  }
}
</script>

<style scoped>
.media-asr-app {
  padding: 16px;
  font-size: 13px;
  color: #333;
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
}

.toolbar {
  background: #f8f9fa;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.toolbar-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.field-label {
  min-width: 68px;
  font-weight: 500;
  color: #555;
  font-size: 12px;
  flex-shrink: 0;
}

.field-label-offset {
  margin-left: 8px;
  font-weight: 500;
  color: #555;
  font-size: 12px;
  flex-shrink: 0;
}

.mode-group {
  display: flex;
  gap: 4px;
}

.mode-btn {
  padding: 5px 14px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  color: #555;
  transition: all 0.15s;
}

.mode-btn.active {
  background: #1677ff;
  color: #fff;
  border-color: #1677ff;
}

.file-input-group {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}

.file-id-input {
  width: 120px;
  padding: 5px 8px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
}

.file-id-input:focus {
  border-color: #1677ff;
}

.file-sep {
  color: #999;
  font-size: 12px;
}

.upload-btn {
  padding: 5px 12px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #fff;
  cursor: pointer;
  font-size: 12px;
  color: #555;
}

.upload-btn:hover {
  border-color: #1677ff;
  color: #1677ff;
}

.uploaded-name {
  font-size: 12px;
  color: #1677ff;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.param-select {
  padding: 5px 8px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 12px;
  background: #fff;
  outline: none;
  cursor: pointer;
}

.lang-input {
  width: 110px;
  padding: 5px 8px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  font-size: 12px;
  outline: none;
}

.lang-input:focus {
  border-color: #1677ff;
}

.exec-btn {
  padding: 6px 24px;
  border: none;
  border-radius: 6px;
  background: #1677ff;
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s;
}

.exec-btn:hover:not(:disabled) {
  background: #0958d9;
}

.exec-btn:disabled {
  background: #a0c4ff;
  cursor: not-allowed;
}

.duration-info {
  font-size: 11px;
  color: #999;
}

.error-bar {
  margin-top: 10px;
  padding: 8px 12px;
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 6px;
  color: #cf1322;
  font-size: 12px;
}

.result-area {
  margin-top: 12px;
}

.result-summary {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.result-badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 500;
}

.result-badge.ok {
  background: #f6ffed;
  color: #389e0d;
  border: 1px solid #b7eb8f;
}

.file-id-badge {
  font-size: 11px;
  color: #1677ff;
  background: #e6f4ff;
  padding: 2px 8px;
  border-radius: 4px;
}

.result-section {
  margin-bottom: 14px;
}

.section-header {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 6px;
  color: #333;
}

.transcript-text {
  background: #fafafa;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow-y: auto;
  margin: 0;
}

.segments-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.segments-table th {
  background: #f5f5f5;
  padding: 6px 10px;
  text-align: left;
  font-weight: 500;
  border-bottom: 2px solid #e5e7eb;
}

.segments-table td {
  padding: 5px 10px;
  border-bottom: 1px solid #f0f0f0;
  vertical-align: top;
}

.col-time {
  width: 70px;
  font-family: 'SF Mono', 'Menlo', monospace;
  font-size: 11px;
  color: #888;
  white-space: nowrap;
}

.meta-section {
  font-size: 11px;
  color: #999;
}
</style>
