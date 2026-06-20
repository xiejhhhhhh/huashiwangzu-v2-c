<template>
  <div class="sandbox-shell">
    <header class="sandbox-header">
      <span class="sandbox-badge">SANDBOX</span>
      <h1 class="sandbox-title">知识库</h1>
      <span class="sandbox-hint">Independent development mode</span>
    </header>
    <main class="sandbox-main">
      <ModuleEntry />
    </main>
  </div>
</template>

<script setup lang="ts">
import ModuleEntry from '@modules/knowledge/frontend/index.vue'
</script>

<style scoped>
.sandbox-shell { display: flex; flex-direction: column; height: 100vh; }
.sandbox-header { display: flex; align-items: center; gap: 12px; padding: 8px 16px; background: #fff; border-bottom: 1px solid #e4e7ed; flex-shrink: 0; }
.sandbox-badge { display: inline-block; background: #409eff; color: #fff; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 3px; }
.sandbox-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.sandbox-hint { font-size: 12px; color: #909399; margin-left: auto; }
.sandbox-main { flex: 1; min-height: 0; overflow: hidden; }
</style>
