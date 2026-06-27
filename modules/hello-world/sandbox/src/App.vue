<template>
  <div class="sandbox-shell">
    <header class="sandbox-header">
      <span class="sandbox-badge">SANDBOX</span>
      <h1 class="sandbox-title">Hello World</h1>
      <span class="sandbox-hint">Independent development mode</span>
    </header>
    <main class="sandbox-main">
      <ModuleEntry />
    </main>
  </div>
</template>

<script setup lang="ts">
// Import your module's frontend entry component.
// If your manifest says "component_key": "index.vue", this is the correct import:
import ModuleEntry from '@modules/hello-world/frontend/index.vue'

// If your manifest uses a different component_key, update the path:
// import ModuleEntry from '@modules/hello-world/frontend/entry.vue'
</script>

<style scoped>
.sandbox-shell { display: flex; flex-direction: column; height: 100%; }
.sandbox-header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #fff; border-bottom: 1px solid #e4e7ed; flex-shrink: 0; }
.sandbox-badge { display: inline-block; background: #409eff; color: #fff; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 3px; }
.sandbox-title { font-size: 15px; font-weight: 600; color: #303133; }
.sandbox-hint { font-size: 12px; color: #909399; margin-left: auto; }
.sandbox-main { flex: 1; overflow: auto; padding: 16px; }
</style>
