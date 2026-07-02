<template>
  <div class="pp-container">
    <div class="pp-header">
      <h3>⚙️ 提示词管理</h3>
      <button class="pp-btn pp-btn-primary" @click="showAddDialog">新增提示词</button>
    </div>

    <div v-if="loading" class="pp-loading">加载中…</div>
    <div v-else>
      <div v-for="cat in categories" :key="cat" class="pp-category">
        <div class="pp-cat-header" @click="toggleCategory(cat)">
          <span class="pp-cat-arrow">{{ expandedCategories[cat] ? '▼' : '▶' }}</span>
          <span class="pp-cat-name">{{ catNames[cat] || cat }}</span>
        </div>
        <div v-if="expandedCategories[cat]" class="pp-cat-body">
          <div v-for="p in groupedPrompts[cat]" :key="p.id" class="pp-item">
            <div class="pp-item-header">
              <span class="pp-item-name">{{ p.name || p.key }}</span>
              <span class="pp-tag">{{ p.key }}</span>
            </div>
            <div class="pp-item-desc" v-if="p.description">{{ p.description }}</div>
            <textarea
              :value="p.content"
              @input="onPromptInput(p, $event)"
              class="pp-item-input"
              rows="4"
            ></textarea>
            <div class="pp-item-actions">
              <button class="pp-btn pp-btn-primary pp-btn-sm" @click="savePrompt(p)">保存</button>
              <button v-if="p.owner_id !== 0" class="pp-btn pp-btn-danger pp-btn-sm" @click="deletePrompt(p)">删除</button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Add dialog -->
    <div v-if="addDialog" class="pp-overlay" @click.self="addDialog = false">
      <div class="pp-dialog">
        <div class="pp-dialog-header">
          <h3>新增提示词</h3>
          <button class="pp-close" @click="addDialog = false">✕</button>
        </div>
        <div class="pp-dialog-body">
          <div class="pp-form">
            <div class="pp-form-row">
              <label>Key：</label>
              <input v-model="newPrompt.key" class="pp-input" placeholder="英文字母key" />
            </div>
            <div class="pp-form-row">
              <label>名称：</label>
              <input v-model="newPrompt.name" class="pp-input" placeholder="中文名称" />
            </div>
            <div class="pp-form-row">
              <label>分类：</label>
              <select v-model="newPrompt.category" class="pp-select">
                <option value="system">系统</option>
                <option value="topic">选题</option>
                <option value="outline">大纲</option>
                <option value="article">成文</option>
                <option value="validation">校验</option>
                <option value="custom">自定义</option>
              </select>
            </div>
            <div class="pp-form-row">
              <label>描述：</label>
              <input v-model="newPrompt.description" class="pp-input" placeholder="用途说明" />
            </div>
            <div class="pp-form-row">
              <label>内容：</label>
              <textarea v-model="newPrompt.content" class="pp-textarea" rows="6" placeholder="提示词模板，可用 {变量} 语法"></textarea>
            </div>
          </div>
        </div>
        <div class="pp-dialog-footer">
          <button class="pp-btn" @click="addDialog = false">取消</button>
          <button class="pp-btn pp-btn-primary" @click="confirmAdd">确认新增</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { apiDelete, apiGet, apiPost } from '../runtime'

interface Prompt {
  id?: number
  key: string
  name: string
  content: string
  description?: string
  category?: string
  owner_id?: number
  _dirty?: boolean
}

const loading = ref(false)
const prompts = ref<Prompt[]>([])
const expandedCategories = ref<Record<string, boolean>>({ system: true })
const addDialog = ref(false)
const newPrompt = ref<Prompt>({ key: '', name: '', category: 'custom', description: '', content: '' })

const catNames: Record<string, string> = {
  system: '系统设置', topic: '选题生成', outline: '大纲生成',
  article: '成文生成', validation: '内容校验', custom: '自定义',
}

const categories = computed(() => {
  const cats = new Set<string>()
  for (const p of prompts.value) {
    if (p.category) cats.add(p.category)
  }
  return Array.from(cats)
})

const groupedPrompts = computed(() => {
  const groups: Record<string, Prompt[]> = {}
  for (const p of prompts.value) {
    const cat = p.category || 'custom'
    if (!groups[cat]) groups[cat] = []
    groups[cat].push(p)
  }
  return groups
})

onMounted(() => loadPrompts())

function toast(msg: string, type: 'success' | 'error' | 'warning' = 'success') {
  const el = document.createElement('div')
  el.style.cssText = 'position:fixed;top:20px;left:50%;transform:translateX(-50%);padding:12px 24px;border-radius:6px;z-index:9999;font-size:14px;'
  el.style.background = type === 'success' ? '#67c23a' : type === 'error' ? '#f56c6c' : '#e6a23c'
  el.style.color = '#fff'
  el.textContent = msg
  document.body.appendChild(el)
  setTimeout(() => el.remove(), 3000)
}

async function loadPrompts() {
  loading.value = true
  try {
    prompts.value = await apiGet<Prompt[]>('/wechat-writer/prompts')
  } catch (e: unknown) {
    console.error('Load prompts error:', e)
    toast(e instanceof Error ? e.message : '提示词加载失败', 'error')
  } finally {
    loading.value = false
  }
}

function toggleCategory(cat: string) {
  expandedCategories.value[cat] = !expandedCategories.value[cat]
}

function onPromptInput(p: Prompt, event: Event) {
  const target = event.target as HTMLTextAreaElement | null
  onPromptChange(p, target?.value ?? '')
}

function onPromptChange(p: Prompt, val: string) {
  p._dirty = true
  p.content = val
}

async function savePrompt(p: Prompt) {
  try {
    await apiPost('/wechat-writer/prompts', { key: p.key, name: p.name, content: p.content, description: p.description, category: p.category })
    toast('已保存', 'success')
    p._dirty = false
  } catch (e: unknown) {
    toast('保存失败：' + (e instanceof Error ? e.message : ''), 'error')
  }
}

async function deletePrompt(p: Prompt) {
  if (!p.id) return
  if (!window.confirm('确定删除此提示词？')) return
  try {
    await apiDelete('/wechat-writer/prompts/' + p.id)
    toast('已删除', 'success')
    loadPrompts()
  } catch (e: unknown) {
    toast(e instanceof Error ? e.message : '删除失败', 'error')
  }
}

function showAddDialog() {
  newPrompt.value = { key: '', name: '', category: 'custom', description: '', content: '' }
  addDialog.value = true
}

async function confirmAdd() {
  try {
    await apiPost('/wechat-writer/prompts', newPrompt.value)
    toast('新增成功', 'success')
    addDialog.value = false
    loadPrompts()
  } catch (e: unknown) {
    toast('新增失败：' + (e instanceof Error ? e.message : ''), 'error')
  }
}
</script>

<style scoped>
.pp-container { padding: 20px; }
.pp-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.pp-header h3 { margin: 0; font-size: 18px; color: #303133; }
.pp-loading { padding: 20px; color: #909399; }
.pp-category { margin-bottom: 8px; border: 1px solid #ebeef5; border-radius: 6px; overflow: hidden; }
.pp-cat-header { padding: 10px 16px; background: #fafafa; cursor: pointer; display: flex; align-items: center; gap: 8px; font-weight: 600; color: #303133; }
.pp-cat-header:hover { background: #f0f5ff; }
.pp-cat-arrow { font-size: 10px; color: #909399; }
.pp-cat-name { font-size: 14px; }
.pp-cat-body { padding: 8px 16px 16px; }
.pp-item { padding: 12px; background: #fff; border: 1px solid #ebeef5; border-radius: 6px; margin-bottom: 8px; }
.pp-item-header { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.pp-item-name { font-weight: 600; color: #303133; font-size: 14px; }
.pp-item-desc { font-size: 12px; color: #909399; margin-bottom: 8px; }
.pp-item-input { width: 100%; padding: 8px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; font-family: inherit; box-sizing: border-box; margin-bottom: 8px; }
.pp-item-actions { display: flex; gap: 8px; }
.pp-tag { display: inline-block; padding: 0 6px; background: #f4f4f5; border-radius: 3px; font-size: 11px; color: #909399; }
.pp-btn { padding: 6px 14px; border: 1px solid #dcdfe6; border-radius: 4px; background: #fff; cursor: pointer; font-size: 13px; }
.pp-btn:hover { border-color: #409eff; color: #409eff; }
.pp-btn-sm { padding: 3px 10px; font-size: 12px; }
.pp-btn-primary { background: #409eff; color: #fff; border-color: #409eff; }
.pp-btn-primary:hover { background: #66b1ff; color: #fff; }
.pp-btn-danger { color: #f56c6c; border-color: #f56c6c; }
.pp-btn-danger:hover { background: #fef0f0; }
.pp-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.4); z-index: 1000; display: flex; align-items: center; justify-content: center; }
.pp-dialog { width: 600px; max-height: 80vh; background: #fff; border-radius: 8px; display: flex; flex-direction: column; }
.pp-dialog-header { display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid #e4e7ed; }
.pp-dialog-header h3 { margin: 0; font-size: 16px; }
.pp-close { border: none; background: none; font-size: 18px; cursor: pointer; color: #909399; }
.pp-dialog-body { flex: 1; padding: 16px 20px; overflow: auto; }
.pp-dialog-footer { padding: 12px 20px; border-top: 1px solid #e4e7ed; display: flex; gap: 8px; justify-content: flex-end; }
.pp-form-row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 12px; }
.pp-form-row label { width: 60px; text-align: right; padding-top: 6px; font-weight: 600; color: #606266; font-size: 13px; }
.pp-input { flex: 1; padding: 6px 10px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; }
.pp-select { flex: 1; padding: 6px 10px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; background: #fff; }
.pp-textarea { flex: 1; padding: 8px; border: 1px solid #dcdfe6; border-radius: 4px; font-size: 13px; font-family: inherit; min-height: 100px; }
</style>
