<template>
  <Teleport to="body">
    <Transition name="launchpad-fade">
      <div v-if="show" class="launchpad-overlay" @mousedown.self="emit('close')" @keydown.esc="emit('close')">
        <section class="launcher-panel desktop-launcher-panel" role="dialog" aria-label="Launchpad">
          <div class="launchpad-search">
            <Search :size="15" />
            <input ref="searchInputRef" v-model="searchText" class="launcher-search-input desktop-launcher-search-input" type="search" placeholder="搜索应用" aria-label="搜索应用" @keydown.escape="handleEscape" />
          </div>
          <div class="launchpad-grid" aria-label="应用">
            <button v-for="app in filteredApps" :key="app.appKey" class="launcher-pinned-item desktop-launcher-app-item" type="button" @click="openApp(app.appKey)">
              <AppIcon :icon="app.icon" :app-key="app.appKey" :size="58" />
              <span>{{ app.appName }}</span>
            </button>
          </div>
          <div v-if="!filteredApps.length" class="launchpad-empty">没有匹配的应用</div>
          <div class="launchpad-page-indicator" aria-hidden="true"><span class="is-active" /></div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { Search } from 'lucide-vue-next'
import type { AppRegistryEntry } from '@/desktop/window-manager/window-types'
import AppIcon from '@/desktop/components/app-icon.vue'

const props = defineProps<{ show: boolean; appList: AppRegistryEntry[] }>()
const emit = defineEmits<{ openApp: [appKey: string]; close: []; executeCommand: [command: string] }>()
const searchText = ref('')
const searchInputRef = ref<HTMLInputElement | null>(null)
const filteredApps = computed(() => {
  const query = searchText.value.trim().toLocaleLowerCase()
  return props.appList.filter(app => app.windowType !== 'background-service' && (!query || `${app.appName} ${app.description}`.toLocaleLowerCase().includes(query)))
})

watch(() => props.show, show => { if (show) { searchText.value = ''; nextTick(() => searchInputRef.value?.focus()) } })
function openApp(appKey: string) { emit('openApp', appKey); emit('close') }
function handleEscape() { if (searchText.value) searchText.value = ''; else emit('close') }
</script>

<style scoped>
.launchpad-overlay{position:fixed;inset:0;z-index:var(--z-launchpad);display:flex;align-items:center;justify-content:center;background:rgba(7,17,28,.2);backdrop-filter:blur(28px) saturate(145%);-webkit-backdrop-filter:blur(28px) saturate(145%)}
.launcher-panel{width:min(1040px,calc(100vw - 48px));height:min(720px,calc(100vh - 72px));display:flex;flex-direction:column;align-items:center;padding:54px 48px 28px;color:white;text-shadow:0 1px 3px rgba(0,0,0,.35)}
.launchpad-search{width:min(260px,100%);height:30px;display:flex;align-items:center;gap:7px;padding:0 10px;margin-bottom:38px;border:1px solid rgba(255,255,255,.24);border-radius:8px;background:rgba(255,255,255,.16);box-shadow:inset 0 1px 0 rgba(255,255,255,.16)}.launcher-search-input{min-width:0;flex:1;border:0;outline:0;background:transparent;color:white;font:var(--desktop-font-body)}.launcher-search-input::placeholder{color:rgba(255,255,255,.72)}
.launchpad-grid{width:100%;display:grid;grid-template-columns:repeat(6,minmax(96px,1fr));gap:30px 22px;align-content:start;overflow:auto;padding:6px 8px}.launcher-pinned-item{height:102px;border:0;background:transparent;color:white;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:8px;border-radius:12px;font:var(--desktop-font-body);text-shadow:0 1px 3px rgba(0,0,0,.55);transition:transform var(--desktop-duration-fast) var(--desktop-ease-standard)}.launcher-pinned-item:hover{transform:scale(1.06)}.launcher-pinned-item:active{transform:scale(.96)}.launcher-pinned-item:focus-visible{outline:2px solid rgba(255,255,255,.9);outline-offset:4px}.launcher-pinned-item span{max-width:112px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.launchpad-empty{margin:auto;color:rgba(255,255,255,.72)}.launchpad-page-indicator{margin-top:auto;height:8px;display:flex;align-items:center}.launchpad-page-indicator span{width:6px;height:6px;border-radius:50%;background:rgba(255,255,255,.38)}.launchpad-page-indicator .is-active{background:white}
.launchpad-fade-enter-active,.launchpad-fade-leave-active{transition:opacity var(--desktop-duration-standard) var(--desktop-ease-standard)}.launchpad-fade-enter-from,.launchpad-fade-leave-to{opacity:0}
@media(max-width:900px){.launchpad-grid{grid-template-columns:repeat(4,minmax(84px,1fr));gap:24px 14px}.launcher-panel{padding-inline:24px}}@media(max-width:620px){.launchpad-grid{grid-template-columns:repeat(3,minmax(76px,1fr))}}
@media(prefers-reduced-motion:reduce){.launchpad-fade-enter-active,.launchpad-fade-leave-active,.launcher-pinned-item{transition:none}.launcher-pinned-item:hover,.launcher-pinned-item:active{transform:none}}
@media(prefers-contrast:more),(prefers-reduced-transparency:reduce){.launchpad-overlay{background:rgba(7,17,28,.94);backdrop-filter:none;-webkit-backdrop-filter:none}}
@supports not ((backdrop-filter:blur(1px)) or (-webkit-backdrop-filter:blur(1px))){.launchpad-overlay{background:rgba(7,17,28,.94)}}
</style>
