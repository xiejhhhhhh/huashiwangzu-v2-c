<template>
  <div class="gp-container">
    <div class="gp-tabs">
      <button
        v-for="s in steps"
        :key="s.key"
        class="gp-tab"
        :class="{ active: step === s.key, disabled: s.disabled }"
        :disabled="s.disabled"
        @click="step = s.key"
      >
        {{ s.label }}
      </button>
    </div>

    <!-- Topic tab -->
    <div v-if="step === 'topic'" class="gp-panel">
      <textarea
        v-model="direction"
        class="gp-textarea"
        rows="3"
        placeholder="输入创作方向，如：敏感肌换季护理、痘痘肌修护、产品成分解析…"
      ></textarea>
      <div class="gp-actions">
        <button class="gp-btn gp-btn-primary" :disabled="topicLoading || !direction.trim()" @click="generateTopics">
          {{ topicLoading ? '生成中…' : '🎯 生成选题' }}
        </button>
      </div>
      <div v-if="topicsResult" class="gp-result">
        <div class="gp-result-content">{{ topicsResult }}</div>
      </div>
    </div>

    <!-- Outline tab -->
    <div v-if="step === 'outline'" class="gp-panel">
      <div class="gp-field">
        <label>选题：</label>
        <input v-model="outlineTopic" class="gp-input" placeholder="选定或手动输入选题" />
      </div>
      <div class="gp-actions">
        <button class="gp-btn gp-btn-primary" :disabled="outlineLoading || !outlineTopic.trim()" @click="generateOutline">
          {{ outlineLoading ? '生成中…' : '📋 生成大纲' }}
        </button>
      </div>
      <div v-if="outlineResult" class="gp-result">
        <div class="gp-result-content">{{ outlineResult }}</div>
        <div class="gp-actions">
          <button class="gp-btn gp-btn-success" @click="goToArticle">按此大纲成文 →</button>
        </div>
      </div>
    </div>

    <!-- Article tab -->
    <div v-if="step === 'article'" class="gp-panel">
      <div class="gp-field">
        <label>选题：</label>
        <input v-model="articleTopic" class="gp-input" placeholder="选题" />
      </div>
      <div class="gp-actions">
        <button class="gp-btn gp-btn-danger" :disabled="articleLoading || !articleTopic.trim()" @click="generateArticle">
          {{ articleLoading ? '生成中…' : '📝 生成文章' }}
        </button>
      </div>
      <div v-if="articleResult" class="gp-result">
        <textarea v-model="articleResult" class="gp-article-text" rows="25"></textarea>
        <div class="gp-actions gp-row">
          <button class="gp-btn gp-btn-primary" :disabled="validateLoading" @click="validateContent">
            {{ validateLoading ? '校验中…' : '🔍 校验成分/功效' }}
          </button>
          <button class="gp-btn gp-btn-success" @click="saveDraft">💾 保存草稿</button>
          <button class="gp-btn" @click="copyContent">📋 复制全文</button>
        </div>
        <div v-if="validateResult" class="gp-validate">
          <h4>校验结果：</h4>
          <div class="gp-validate-content">{{ validateResult }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { apiPost, platform } from '../runtime'

interface TopicResult {
  topics?: string
}

interface OutlineResult {
  outline?: string
}

interface ArticleResult {
  article?: string
}

interface ValidationResult {
  has_knowledge_base_results?: boolean
  knowledge_results?: unknown[]
  ai_validation?: string
}

const steps = [
  { key: 'topic', label: '① 选题', disabled: false },
  { key: 'outline', label: '② 大纲', disabled: false },
  { key: 'article', label: '③ 成文', disabled: false },
]

const step = ref('topic')
const direction = ref('')
const topicLoading = ref(false)
const topicsResult = ref('')
const outlineTopic = ref('')
const outlineLoading = ref(false)
const outlineResult = ref('')
const articleTopic = ref('')
const articleOutline = ref('')
const articleLoading = ref(false)
const articleResult = ref('')
const validateLoading = ref(false)
const validateResult = ref('')

function toast(msg: string, type: 'success' | 'error' | 'warning' = 'success') {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:6px;z-index:9999;font-size:14px;'
  el.style.background = type === 'success' ? '#67c23a' : type === 'error' ? '#f56c6c' : '#e6a23c'
  el.style.color = '#fff'
  el.textContent = msg
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

function errorMessage(e: unknown): string {
  return e instanceof Error ? e.message : '未知错误'
}

async function generateTopics() {
  if (!direction.value.trim()) return
  topicLoading.value = true
  topicsResult.value = ''
  try {
    const result = await platform.modules.call('wechat-writer', 'generate_topics', {
      direction: direction.value,
    }) as TopicResult
    topicsResult.value = result.topics || ''
  } catch (e: unknown) {
    topicsResult.value = '生成失败：' + errorMessage(e)
  } finally {
    topicLoading.value = false
  }
}

async function generateOutline() {
  if (!outlineTopic.value.trim()) return
  outlineLoading.value = true
  outlineResult.value = ''
  try {
    const result = await platform.modules.call('wechat-writer', 'generate_outline', {
      topic: outlineTopic.value,
      direction: direction.value,
    }) as OutlineResult
    outlineResult.value = result.outline || ''
  } catch (e: unknown) {
    outlineResult.value = '生成失败：' + errorMessage(e)
  } finally {
    outlineLoading.value = false
  }
}

function goToArticle() {
  articleTopic.value = outlineTopic.value
  articleOutline.value = outlineResult.value
  step.value = 'article'
}

async function generateArticle() {
  if (!articleTopic.value.trim()) return
  articleLoading.value = true
  articleResult.value = ''
  try {
    const result = await platform.modules.call('wechat-writer', 'generate_article', {
      topic: articleTopic.value,
      outline: articleOutline.value,
      direction: direction.value,
    }) as ArticleResult
    articleResult.value = result.article || ''
  } catch (e: unknown) {
    articleResult.value = '生成失败：' + errorMessage(e)
  } finally {
    articleLoading.value = false
  }
}

async function validateContent() {
  if (!articleResult.value) return
  validateLoading.value = true
  validateResult.value = ''
  try {
    const content = articleResult.value.substring(0, 2000)
    const result = await platform.modules.call('wechat-writer', 'validate_content', { content }) as ValidationResult
    let text = ''
    if (result.has_knowledge_base_results) {
      text += '✅ 知识库匹配到 ' + (result.knowledge_results?.length ?? 0) + ' 条相关结果\n'
    } else {
      text += 'ℹ️ 知识库无直接匹配（知识库内容待补充）\n'
    }
    text += '\n--- AI 校验 ---\n' + (result.ai_validation || '')
    validateResult.value = text
  } catch (e: unknown) {
    validateResult.value = '校验失败：' + errorMessage(e)
  } finally {
    validateLoading.value = false
  }
}

async function saveDraft() {
  try {
    await apiPost('/wechat-writer/drafts', {
      title: articleTopic.value,
      content: articleResult.value,
      outline: { text: articleOutline.value },
      article_type: direction.value.substring(0, 100),
      status: 'draft',
    })
    toast('草稿已保存！', 'success')
  } catch (e: unknown) {
    toast('保存失败：' + errorMessage(e), 'error')
  }
}

async function copyContent() {
  try {
    await navigator.clipboard.writeText(articleResult.value)
    toast('已复制到剪贴板', 'success')
  } catch {
    toast('复制失败，请手动复制', 'warning')
  }
}
</script>

<style scoped>
.gp-container { padding: 20px; height: 100%; overflow: auto; }
.gp-tabs { display: flex; gap: 0; margin-bottom: 20px; border-bottom: 2px solid #e4e7ed; }
.gp-tab { padding: 8px 20px; border: none; background: none; cursor: pointer; font-size: 14px; color: #909399; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.gp-tab.active { color: #409eff; border-bottom-color: #409eff; font-weight: 600; }
.gp-tab.disabled { color: #c0c4cc; cursor: not-allowed; }
.gp-panel { max-width: 900px; }
.gp-textarea { width: 100%; padding: 10px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 14px; font-family: inherit; resize: vertical; box-sizing: border-box; }
.gp-field { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.gp-field label { white-space: nowrap; font-weight: 600; color: #606266; }
.gp-input { flex: 1; padding: 8px 12px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 14px; }
.gp-actions { margin: 12px 0; display: flex; gap: 8px; flex-wrap: wrap; }
.gp-row { display: flex; gap: 8px; flex-wrap: wrap; }
.gp-btn { padding: 8px 16px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; cursor: pointer; font-size: 14px; color: #606266; }
.gp-btn:hover { border-color: #409eff; color: #409eff; }
.gp-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.gp-btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.gp-btn-primary:hover { background: #66b1ff; color: #fff; }
.gp-btn-success { background: #67c23a; color: #fff; border-color: #67c23a; }
.gp-btn-success:hover { background: #85ce61; color: #fff; }
.gp-btn-danger { background: #f56c6c; color: #fff; border-color: #f56c6c; }
.gp-btn-danger:hover { background: #f78989; color: #fff; }
.gp-result { margin-top: 16px; }
.gp-result-content { padding: 16px; background: #fff; border: 1px solid #e4e7ed; border-radius: 6px; line-height: 1.8; white-space: pre-wrap; font-size: 14px; }
.gp-article-text { width: 100%; padding: 12px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 14px; line-height: 1.8; font-family: inherit; box-sizing: border-box; }
.gp-validate { margin-top: 12px; padding: 12px; background: #fef0f0; border: 1px solid #fbc4c4; border-radius: 6px; }
.gp-validate h4 { margin: 0 0 8px; color: #f56c6c; }
.gp-validate-content { white-space: pre-wrap; font-size: 13px; line-height: 1.6; }
</style>
