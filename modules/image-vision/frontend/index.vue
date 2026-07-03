<template>
  <section class="image-vision">
    <header class="toolbar">
      <div class="title-group">
        <p class="eyebrow">Image Vision</p>
        <h2>Local-first analysis</h2>
      </div>
      <div class="controls">
        <label class="field">
          <span>File ID</span>
          <input v-model.number="fileId" min="1" type="number" />
        </label>
        <label class="field">
          <span>Mode</span>
          <select v-model="analysisMode">
            <option value="auto">auto</option>
            <option value="local">local</option>
            <option value="semantic">semantic</option>
          </select>
        </label>
        <button :disabled="loading || fileId <= 0" type="button" @click="runAnalysis">
          {{ loading ? 'Analyzing' : 'Analyze' }}
        </button>
      </div>
    </header>

    <main class="content">
      <section class="summary-panel">
        <h3>Result</h3>
        <p v-if="!result && !error" class="muted">No analysis yet.</p>
        <p v-if="error" class="error">{{ error }}</p>
        <pre v-if="result" class="description">{{ result.description }}</pre>
      </section>

      <section class="details-grid">
        <article class="panel">
          <h3>Strategy</h3>
          <dl v-if="result" class="strategy">
            <div>
              <dt>Mode</dt>
              <dd>{{ result.analysis_strategy.mode }}</dd>
            </div>
            <div>
              <dt>VLM attempted</dt>
              <dd>{{ result.analysis_strategy.vlm_attempted ? 'yes' : 'no' }}</dd>
            </div>
            <div>
              <dt>VLM used</dt>
              <dd>{{ result.analysis_strategy.vlm_used ? 'yes' : 'no' }}</dd>
            </div>
            <div>
              <dt>External calls</dt>
              <dd>{{ result.analysis_strategy.external_vlm_calls }}</dd>
            </div>
            <div>
              <dt>Decision</dt>
              <dd>{{ result.analysis_strategy.vlm_decision.reason }}</dd>
            </div>
          </dl>
          <p v-else class="muted">Waiting for a file.</p>
        </article>

        <article class="panel">
          <h3>Warnings</h3>
          <ul v-if="result && result.warnings.length" class="warnings">
            <li v-for="warning in result.warnings" :key="warning">{{ warning }}</li>
          </ul>
          <p v-else class="muted">None</p>
        </article>
      </section>

      <section class="facts-panel">
        <h3>Local Facts</h3>
        <pre v-if="result" class="facts">{{ prettyFacts }}</pre>
        <p v-else class="muted">Local facts will appear here.</p>
      </section>
    </main>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { initRuntime, platform } from '../runtime'

type AnalysisMode = 'auto' | 'local' | 'semantic'

interface VlmDecision {
  use_vlm: boolean
  reason: string
}

interface AnalysisStrategy {
  mode: string
  vlm_attempted: boolean
  vlm_used: boolean
  external_vlm_calls: number
  vlm_decision: VlmDecision
}

interface DescribeResult {
  description: string
  local_analysis: Record<string, unknown>
  analysis_strategy: AnalysisStrategy
  warnings: string[]
}

const fileId = ref(0)
const analysisMode = ref<AnalysisMode>('auto')
const loading = ref(false)
const error = ref('')
const result = ref<DescribeResult | null>(null)

const prettyFacts = computed(() => (
  result.value ? JSON.stringify(result.value.local_analysis, null, 2) : ''
))

onMounted(async () => {
  await initRuntime('image-vision')
  const openPayload = platform.files.getOpenPayload()
  if (openPayload?.fileId) {
    fileId.value = openPayload.fileId
  }
})

async function runAnalysis(): Promise<void> {
  error.value = ''
  result.value = null
  loading.value = true
  try {
    const payload = {
      file_id: fileId.value,
      analysis_mode: analysisMode.value,
    }
    const rawResult = await platform.modules.call('image-vision', 'describe', payload)
    result.value = parseDescribeResult(rawResult)
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : 'Analysis failed'
  } finally {
    loading.value = false
  }
}

function parseDescribeResult(value: unknown): DescribeResult {
  if (!isRecord(value)) {
    throw new Error('Invalid analysis result')
  }
  const strategy = value.analysis_strategy
  if (!isRecord(strategy)) {
    throw new Error('Invalid analysis strategy')
  }
  const decision = strategy.vlm_decision
  if (!isRecord(decision)) {
    throw new Error('Invalid VLM decision')
  }
  const localAnalysis = value.local_analysis
  if (!isRecord(localAnalysis)) {
    throw new Error('Invalid local analysis')
  }
  return {
    description: asString(value.description),
    local_analysis: localAnalysis,
    analysis_strategy: {
      mode: asString(strategy.mode),
      vlm_attempted: asBoolean(strategy.vlm_attempted),
      vlm_used: asBoolean(strategy.vlm_used),
      external_vlm_calls: asNumber(strategy.external_vlm_calls),
      vlm_decision: {
        use_vlm: asBoolean(decision.use_vlm),
        reason: asString(decision.reason),
      },
    },
    warnings: asStringArray(value.warnings),
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function asBoolean(value: unknown): boolean {
  return typeof value === 'boolean' ? value : false
}

function asNumber(value: unknown): number {
  return typeof value === 'number' ? value : 0
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}
</script>

<style scoped>
.image-vision {
  min-height: 100%;
  color: #18212f;
  background: #f6f8fb;
}

.toolbar {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 20px;
  border-bottom: 1px solid #d8dee8;
  background: #ffffff;
}

.title-group {
  display: grid;
  gap: 4px;
}

.eyebrow {
  margin: 0;
  color: #5b6b80;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: uppercase;
}

h2,
h3 {
  margin: 0;
  letter-spacing: 0;
}

h2 {
  font-size: 22px;
  line-height: 1.2;
}

h3 {
  font-size: 14px;
  line-height: 1.3;
}

.controls {
  display: flex;
  align-items: end;
  gap: 10px;
  flex-wrap: wrap;
}

.field {
  display: grid;
  gap: 5px;
  color: #536276;
  font-size: 12px;
  font-weight: 600;
}

input,
select,
button {
  height: 34px;
  border-radius: 6px;
  border: 1px solid #c9d2df;
  background: #ffffff;
  color: #18212f;
  font: inherit;
}

input,
select {
  min-width: 128px;
  padding: 0 10px;
}

button {
  min-width: 96px;
  padding: 0 14px;
  border-color: #275efe;
  background: #275efe;
  color: #ffffff;
  font-weight: 700;
  cursor: pointer;
}

button:disabled {
  border-color: #b9c2d0;
  background: #b9c2d0;
  cursor: not-allowed;
}

.content {
  display: grid;
  gap: 14px;
  padding: 16px 20px 24px;
}

.summary-panel,
.facts-panel,
.panel {
  border: 1px solid #d8dee8;
  border-radius: 8px;
  background: #ffffff;
  padding: 14px;
}

.details-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(220px, 0.6fr);
  gap: 14px;
}

.description,
.facts {
  overflow: auto;
  margin: 12px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  color: #233145;
  font-size: 13px;
  line-height: 1.6;
}

.facts {
  max-height: 340px;
  white-space: pre;
}

.muted {
  margin: 12px 0 0;
  color: #748297;
  font-size: 13px;
}

.error {
  margin: 12px 0 0;
  color: #b42318;
  font-size: 13px;
  font-weight: 600;
}

.strategy {
  display: grid;
  gap: 8px;
  margin: 12px 0 0;
}

.strategy div {
  display: grid;
  grid-template-columns: 128px minmax(0, 1fr);
  gap: 10px;
}

dt {
  color: #66758b;
  font-size: 12px;
}

dd {
  margin: 0;
  color: #1f2a3a;
  font-size: 13px;
  word-break: break-word;
}

.warnings {
  margin: 12px 0 0;
  padding-left: 18px;
  color: #8a5a00;
  font-size: 13px;
  line-height: 1.5;
}

@media (max-width: 720px) {
  .toolbar {
    align-items: stretch;
    flex-direction: column;
  }

  .controls,
  .field,
  input,
  select,
  button {
    width: 100%;
  }

  .details-grid {
    grid-template-columns: 1fr;
  }

  .strategy div {
    grid-template-columns: 1fr;
    gap: 3px;
  }
}
</style>
