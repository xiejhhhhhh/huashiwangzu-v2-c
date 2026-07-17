<template>
  <div class="settings-shell">
    <header class="settings-header">
      <h1>设置</h1>
      <p class="hint">Product Runtime settings shell (WP4/WP6). Preferences wiring comes later.</p>
    </header>
    <main class="settings-body">
      <section class="card">
        <h2>桌面</h2>
        <p>窗口状态 CAS、Product 分组与外观偏好将挂在这里。</p>
      </section>
      <section class="card">
        <h2>产品目录</h2>
        <p>仅展示 Product，不展示 Parser/Provider/Service。</p>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
// Platform settings product entry — skeleton for Product Catalog.
</script>

<style scoped>
.settings-shell { display:flex; flex-direction:column; height:100%; background:#f7f8fa; color:#1f2329; }
.settings-header { padding:12px 16px; border-bottom:1px solid #e5e7eb; background:#fff; }
.settings-header h1 { margin:0; font-size:16px; font-weight:600; }
.hint { margin:4px 0 0; font-size:12px; color:#6b7280; }
.settings-body { flex:1; overflow:auto; padding:16px; display:grid; gap:12px; }
.card { background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:14px 16px; }
.card h2 { margin:0 0 6px; font-size:14px; }
.card p { margin:0; font-size:12px; color:#6b7280; }
</style>
