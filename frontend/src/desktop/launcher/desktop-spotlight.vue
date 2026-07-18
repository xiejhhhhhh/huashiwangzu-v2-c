<template>
  <Teleport to="body">
    <Transition name="spotlight-fade">
      <div v-if="show" class="spotlight-overlay" @mousedown.self="emit('close')">
        <section class="spotlight-panel glass-spotlight" role="dialog" aria-label="Spotlight">
          <div class="spotlight-search-row">
            <Search :size="24" />
            <input ref="inputRef" v-model="searchText" class="spotlight-input" type="search" placeholder="Spotlight 搜索" aria-label="Spotlight 搜索" @keydown.escape="emit('close')" @keydown.down.prevent="moveSelection(1)" @keydown.up.prevent="moveSelection(-1)" @keydown.enter.prevent="executeSelected" />
            <kbd>esc</kbd>
          </div>
          <div v-if="results.length" class="spotlight-results" role="listbox">
            <button v-for="(item, index) in results" :key="item.id" class="spotlight-result" :class="{ 'is-selected': index === selectedIndex }" type="button" role="option" :aria-selected="index === selectedIndex" @mouseenter="selectedIndex = index" @click="execute(item)">
              <span v-if="systemIcon(item)" class="spotlight-system-icon"><component :is="systemIcon(item)" :size="22" :stroke-width="1.8" /></span>
              <AppIcon v-else :icon="item.icon || fallbackIcon(item.type)" :app-key="resultAppKey(item)" :size="34" />
              <span class="spotlight-result-copy"><strong>{{ item.title }}</strong><small>{{ item.description || resultKindLabel(item.type) }}</small></span>
              <span class="spotlight-kind">{{ resultKindLabel(item.type) }}</span>
            </button>
          </div>
          <div v-else-if="searchText.trim()" class="spotlight-empty">没有找到结果</div>
          <div v-else class="spotlight-empty">输入应用、文件或命令名称</div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { FileText, Folder, LogOut, Maximize2, Minimize2, RefreshCw, Search } from 'lucide-vue-next'
import AppIcon from '@/desktop/components/app-icon.vue'
import { commandRegistry, type SearchResultItem } from '@/desktop/app-registry/command-registry'

const props = defineProps<{ show: boolean }>()
const emit = defineEmits<{ close: [] }>()
const searchText = ref('')
const inputRef = ref<HTMLInputElement | null>(null)
const selectedIndex = ref(0)
const results = computed(() => commandRegistry.search(searchText.value.trim()).slice(0, 9))

watch(() => props.show, (show) => {
  if (!show) return
  searchText.value = ''
  selectedIndex.value = 0
  nextTick(() => inputRef.value?.focus())
})
watch(results, () => { selectedIndex.value = 0 })

function moveSelection(delta: number) {
  if (!results.value.length) return
  selectedIndex.value = (selectedIndex.value + delta + results.value.length) % results.value.length
}
function executeSelected() { const item = results.value[selectedIndex.value]; if (item) execute(item) }
function execute(item: SearchResultItem) { void item.execute(); emit('close') }
function fallbackIcon(type: SearchResultItem['type']) { return type === 'file' ? 'Document' : type === 'app' ? 'Grid' : 'Search' }
function resultAppKey(item: SearchResultItem) { return item.id.startsWith('app:') ? item.id.split(':')[1] : '' }
const systemIcons = { Document: FileText, Folder, LogOut, Maximize2, Minimize2, RefreshCw }
function systemIcon(item: SearchResultItem) { return item.type === 'app' || item.type === 'background-capability' ? null : systemIcons[item.icon as keyof typeof systemIcons] || Search }
function resultKindLabel(type: SearchResultItem['type']) { return type === 'app' ? '应用' : type === 'file' ? '文件' : type === 'background-capability' ? '后台能力' : '命令' }
</script>

<style scoped>
.spotlight-overlay{position:fixed;inset:0;z-index:var(--z-spotlight);display:flex;justify-content:center;align-items:flex-start;padding-top:min(18vh,160px);background:rgba(4,9,18,.08)}
.spotlight-panel{width:min(680px,calc(100vw - 32px));overflow:hidden;color:var(--desktop-ink)}
.spotlight-search-row{height:64px;display:flex;align-items:center;gap:13px;padding:0 18px;border-bottom:1px solid var(--desktop-divider)}.spotlight-input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:inherit;font-size:22px;font-family:inherit}.spotlight-input::placeholder{color:var(--desktop-ink-muted)}.spotlight-search-row kbd{padding:2px 6px;border:1px solid var(--desktop-divider);border-radius:5px;color:var(--desktop-ink-muted);font:var(--desktop-font-caption)}
.spotlight-results{padding:7px;max-height:min(480px,60vh);overflow:auto}.spotlight-result{width:100%;height:54px;display:flex;align-items:center;gap:11px;padding:0 10px;border:0;border-radius:9px;background:transparent;color:inherit;text-align:left}.spotlight-result.is-selected{background:var(--desktop-selection);color:white}.spotlight-system-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:8px;background:rgba(60,60,67,.1);flex:0 0 34px}.spotlight-result.is-selected .spotlight-system-icon{background:rgba(255,255,255,.2)}.spotlight-result-copy{min-width:0;flex:1;display:flex;flex-direction:column}.spotlight-result-copy strong{font:var(--desktop-font-body);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.spotlight-result-copy small{font:var(--desktop-font-caption);opacity:.68;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.spotlight-kind{font:var(--desktop-font-caption);opacity:.7}.spotlight-empty{padding:34px;text-align:center;color:var(--desktop-ink-muted);font:var(--desktop-font-body)}
.spotlight-fade-enter-active,.spotlight-fade-leave-active{transition:opacity var(--desktop-duration-standard) var(--desktop-ease-standard)}.spotlight-fade-enter-from,.spotlight-fade-leave-to{opacity:0}.spotlight-fade-enter-active .spotlight-panel{transition:transform var(--desktop-duration-standard) var(--desktop-ease-standard),opacity var(--desktop-duration-fast)}.spotlight-fade-enter-from .spotlight-panel{transform:scale(.96) translateY(-10px);opacity:0}
@media(prefers-reduced-motion:reduce){.spotlight-fade-enter-active,.spotlight-fade-leave-active,.spotlight-fade-enter-active .spotlight-panel{transition:none}}
</style>
