<template>
  <div
    class="media-intelligence-app"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="utility"
  >
    <MacAppShell layout="utility">
      <template #toolbar>
        <div class="media-toolbar">
          <strong>媒体</strong>
          <span>图片与音视频轻分析</span>
        </div>
      </template>
      <div class="media-body">
    <aside class="panel">
      <div class="field">
        <label>Action</label>
        <select v-model="action">
          <option value="analyze_image">Analyze image</option>
          <option value="analyze_video">Analyze video</option>
          <option value="extract_keyframes">Extract keyframes</option>
          <option value="ocr">OCR</option>
          <option value="embed_image">Embed image</option>
          <option value="detect_objects">Detect objects</option>
          <option value="summarize_media">Summarize media</option>
        </select>
      </div>

      <div class="field">
        <label>File ID</label>
        <input v-model.number="fileId" min="1" type="number" />
      </div>

      <div v-if="action === 'extract_keyframes' || action === 'analyze_video'" class="field">
        <label>Max keyframes</label>
        <input v-model.number="maxKeyframes" min="1" max="12" type="number" />
      </div>

      <div v-if="action === 'embed_image'" class="field">
        <label>Embedding dimensions</label>
        <input v-model.number="dimensions" min="8" max="1024" type="number" />
      </div>

      <label class="toggle">
        <input v-model="refine" type="checkbox" />
        <span>VLM refine</span>
      </label>

      <label class="toggle">
        <input v-model="includeEmbedding" type="checkbox" />
        <span>Include image embedding</span>
      </label>

      <button class="run-button" :disabled="running || fileId <= 0" @click="runAnalysis">
        {{ running ? 'Running...' : 'Run' }}
      </button>

      <p v-if="errorMessage" class="error">{{ errorMessage }}</p>
    </aside>

    <main class="result">
      <div v-if="!resultText" class="empty">Run an action to inspect the media analysis contract.</div>
      <pre v-else>{{ resultText }}</pre>
    </main>
      </div>
    </MacAppShell>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { MacAppShell } from '@/desktop/app-kit'
import { initRuntime, platform } from '../runtime'

type MediaAction =
  | 'analyze_image'
  | 'analyze_video'
  | 'extract_keyframes'
  | 'ocr'
  | 'embed_image'
  | 'detect_objects'
  | 'summarize_media'

const action = ref<MediaAction>('analyze_image')
const fileId = ref(0)
const maxKeyframes = ref(5)
const dimensions = ref(32)
const refine = ref(true)
const includeEmbedding = ref(false)
const running = ref(false)
const errorMessage = ref('')
const result = ref<unknown>(null)

const resultText = computed(() => (result.value ? JSON.stringify(result.value, null, 2) : ''))

onMounted(() => {
  void initRuntime()
})

function buildParameters(): Record<string, unknown> {
  const parameters: Record<string, unknown> = {
    file_id: fileId.value,
  }
  if (action.value === 'analyze_image') {
    parameters.include_embedding = includeEmbedding.value
    parameters.refine = refine.value
  }
  if (action.value === 'analyze_video') {
    parameters.max_keyframes = maxKeyframes.value
    parameters.refine = refine.value
  }
  if (action.value === 'extract_keyframes') {
    parameters.max_keyframes = maxKeyframes.value
  }
  if (action.value === 'embed_image') {
    parameters.dimensions = dimensions.value
  }
  return parameters
}

async function runAnalysis(): Promise<void> {
  running.value = true
  errorMessage.value = ''
  result.value = null
  try {
    result.value = await platform.modules.call('media-intelligence', action.value, buildParameters())
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'Request failed'
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.media-intelligence-app {
  height: 100%;
  min-height: 0;
  background: var(--mac-app-surface, #f8fafc);
  color: var(--mac-app-text, #1f2937);
}
.media-toolbar {
  display: grid;
  gap: 1px;
  min-height: var(--mac-app-toolbar-height, 42px);
  align-content: center;
  padding: 0 4px;
  width: 100%;
}
.media-toolbar strong { font: var(--mac-app-font-title, 600 13px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif); }
.media-toolbar span { font: var(--mac-app-font-caption, 400 11px/1.35 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif); color: var(--mac-app-text-secondary, #6b7280); }
.media-body {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  height: 100%;
  min-height: 0;
}

.panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 18px;
  border-right: 1px solid #d8dde6;
  background: #ffffff;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

label {
  font-size: 12px;
  font-weight: 600;
  color: #52606d;
}

select,
input {
  height: 34px;
  border: 1px solid #cbd2d9;
  border-radius: 6px;
  padding: 0 10px;
  background: #ffffff;
  color: #1f2933;
}

.toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.toggle input {
  width: 16px;
  height: 16px;
}

.run-button {
  height: 36px;
  border: 0;
  border-radius: 6px;
  background: #2563eb;
  color: #ffffff;
  font-weight: 700;
  cursor: pointer;
}

.run-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.error {
  margin: 0;
  color: #b42318;
  font-size: 13px;
}

.result {
  min-width: 0;
  padding: 18px;
  overflow: auto;
}

.empty {
  color: #6b7280;
  font-size: 14px;
}

pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 12px;
  line-height: 1.5;
  color: #111827;
}

@media (max-width: 760px) {
  .media-body {
    grid-template-columns: 1fr;
  }

  .panel {
    border-right: 0;
    border-bottom: 1px solid #d8dde6;
  }
}
</style>
