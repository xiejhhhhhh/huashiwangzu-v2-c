<template>
  <div
    class="settings-app"
    data-mac-app-kit="mac-app-v1"
    data-mac-app-layout="settings"
  >
    <MacAppShell layout="settings" :sidebar-width="200">
      <template #sidebar>
        <nav class="settings-nav" aria-label="设置分类">
          <button
            v-for="item in sections"
            :key="item.id"
            type="button"
            class="settings-nav-item"
            :class="{ active: activeSection === item.id }"
            @click="activeSection = item.id"
          >
            <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </button>
        </nav>
      </template>

      <template #toolbar>
        <div class="settings-toolbar">
          <strong>{{ currentSection.label }}</strong>
          <span>{{ currentSection.hint }}</span>
        </div>
      </template>

      <div class="settings-body">
        <section v-if="activeSection === 'desktop'" class="settings-panel">
          <h2>桌面</h2>
          <p class="panel-desc">壳层外观与桌面基础偏好。Win11 完整壳另立阶段，当前仅切换视觉皮肤 token。</p>

          <div class="form-row">
            <div class="form-copy">
              <strong>壳皮肤</strong>
              <span>默认 macOS；win11 仅插槽皮肤，不改变运行时行为。</span>
            </div>
            <select
              class="mac-select"
              :value="config.shellSkin"
              @change="onShellSkinChange(($event.target as HTMLSelectElement).value)"
            >
              <option value="macos">macOS</option>
              <option value="win11">Windows 11（预览）</option>
            </select>
          </div>

          <div class="form-row">
            <div class="form-copy">
              <strong>操作反馈</strong>
              <span>桌面 toast / 操作提示开关。</span>
            </div>
            <label class="mac-switch">
              <input
                type="checkbox"
                :checked="config.enableOperationToast"
                @change="updateConfig({ enableOperationToast: ($event.target as HTMLInputElement).checked })"
              >
              <span>{{ config.enableOperationToast ? '开' : '关' }}</span>
            </label>
          </div>
        </section>

        <section v-else-if="activeSection === 'hotkeys'" class="settings-panel">
          <h2>快捷键</h2>
          <p class="panel-desc">Web 场景默认不抢浏览器 / 系统快捷键。需要增强时再显式打开。</p>

          <div class="form-row">
            <div class="form-copy">
              <strong>启用桌面快捷键</strong>
              <span>关闭时：⌘/Ctrl+Space、⌘/Ctrl+Tab 等不拦截。开启后仅处理不冲突组合（如 ⌃⇧Space）。</span>
            </div>
            <label class="mac-switch">
              <input
                type="checkbox"
                :checked="config.enableDesktopHotkeys"
                @change="onHotkeysChange(($event.target as HTMLInputElement).checked)"
              >
              <span>{{ config.enableDesktopHotkeys ? '开' : '关' }}</span>
            </label>
          </div>

          <div class="hint-card">
            <strong>建议键位（开启后）</strong>
            <ul>
              <li>⌃⇧Space · Spotlight</li>
              <li>⌃⇧` · App Switcher</li>
            </ul>
            <p>菜单点击与 Dock 按钮始终可用，不依赖快捷键。</p>
          </div>
        </section>

        <section v-else class="settings-panel">
          <h2>产品目录</h2>
          <p class="panel-desc">桌面只展示 Product，不展示 Parser / Provider / Service 能力节点。</p>
          <div class="hint-card">
            <strong>UI 契约</strong>
            <p>新软件必须声明 <code>uiContract.kit = mac-app-v1</code>，入口使用 <code>MacAppShell</code>，反馈走 <code>useAppFeedback</code>。</p>
          </div>
        </section>
      </div>
    </MacAppShell>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { MacAppShell, useAppFeedback } from '@/desktop/app-kit'
import { useDesktopConfig } from '@/desktop/config/desktop-preferences'

// Platform settings product entry — mac settings shell for desktop prefs.
const feedback = useAppFeedback()
const { config, updateConfig, setShellSkin } = useDesktopConfig()

const sections = [
  { id: 'desktop', label: '桌面', icon: '🖥', hint: '外观与桌面反馈' },
  { id: 'hotkeys', label: '快捷键', icon: '⌨', hint: 'Web 友好热键策略' },
  { id: 'products', label: '产品', icon: '📦', hint: 'Product Catalog 说明' },
] as const

type SectionId = typeof sections[number]['id']
const activeSection = ref<SectionId>('desktop')

const currentSection = computed(() =>
  sections.find(item => item.id === activeSection.value) || sections[0],
)

function onShellSkinChange(value: string) {
  if (value !== 'macos' && value !== 'win11') return
  setShellSkin(value)
  feedback.success(value === 'macos' ? '已切换到 macOS 皮肤' : '已切换到 Win11 预览皮肤')
}

function onHotkeysChange(enabled: boolean) {
  updateConfig({ enableDesktopHotkeys: enabled })
  feedback.info(enabled ? '已启用桌面快捷键（仍避免抢浏览器常用键）' : '已关闭桌面快捷键抢占')
}
</script>

<style scoped>
.settings-app {
  height: 100%;
  min-height: 0;
  color: var(--mac-app-text);
  background: var(--mac-app-surface);
}

.settings-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
  height: 100%;
  padding: 10px 8px;
  box-sizing: border-box;
}

.settings-nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  border: 0;
  background: transparent;
  border-radius: var(--mac-app-radius-control);
  padding: 8px 10px;
  text-align: left;
  font: var(--mac-app-font);
  color: var(--mac-app-text);
  cursor: pointer;
}

.settings-nav-item:hover {
  background: color-mix(in srgb, var(--mac-app-accent) 8%, transparent);
}

.settings-nav-item.active {
  background: var(--mac-app-selection);
  color: var(--mac-app-accent);
  font-weight: 600;
}

.nav-icon {
  width: 18px;
  text-align: center;
  opacity: 0.9;
}

.settings-toolbar {
  display: grid;
  gap: 1px;
  min-height: var(--mac-app-toolbar-height);
  align-content: center;
  padding: 0 4px;
}

.settings-toolbar strong {
  font: var(--mac-app-font-title);
}

.settings-toolbar span {
  font: var(--mac-app-font-caption);
  color: var(--mac-app-text-secondary);
}

.settings-body {
  height: 100%;
  min-height: 0;
  overflow: auto;
  padding: 18px 20px;
  box-sizing: border-box;
}

.settings-panel {
  max-width: 720px;
  display: grid;
  gap: 14px;
}

.settings-panel h2 {
  margin: 0;
  font: 600 16px/1.3 -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", sans-serif;
}

.panel-desc {
  margin: 0;
  font-size: 12px;
  color: var(--mac-app-text-secondary);
}

.form-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px;
  border: 1px solid var(--mac-app-border);
  border-radius: var(--mac-app-radius-card);
  background: color-mix(in srgb, var(--mac-app-surface) 72%, white);
}

.form-copy {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.form-copy strong {
  font-size: 13px;
  font-weight: 600;
}

.form-copy span {
  font-size: 11px;
  color: var(--mac-app-text-secondary);
  line-height: 1.4;
}

.mac-select {
  min-width: 150px;
  height: 30px;
  border: 1px solid var(--mac-app-border-strong);
  border-radius: var(--mac-app-radius-control);
  background: #fff;
  color: var(--mac-app-text);
  padding: 0 8px;
  font-size: 12px;
}

.mac-switch {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--mac-app-text-secondary);
  cursor: pointer;
  user-select: none;
}

.mac-switch input {
  width: 16px;
  height: 16px;
  accent-color: var(--mac-app-accent);
}

.hint-card {
  padding: 12px 14px;
  border-radius: var(--mac-app-radius-card);
  border: 1px solid var(--mac-app-border);
  background: color-mix(in srgb, var(--mac-app-accent) 6%, white);
  display: grid;
  gap: 6px;
}

.hint-card strong {
  font-size: 12px;
}

.hint-card p,
.hint-card ul {
  margin: 0;
  font-size: 12px;
  color: var(--mac-app-text-secondary);
}

.hint-card ul {
  padding-left: 18px;
}

.hint-card code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: var(--mac-app-text);
}
</style>
