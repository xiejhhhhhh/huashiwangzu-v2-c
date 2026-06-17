<template>
  <section class="platform-app-placeholder">
    <header class="platform-app-placeholder_header">
      <div>
        <p class="platform-app-placeholder_kicker">Platform app</p>
        <h2 class="platform-app-placeholder_title">{{ appName }}</h2>
      </div>
      <span class="platform-app-placeholder_status">{{ status }}</span>
    </header>

    <p class="platform-app-placeholder_message">
      {{ message }}
    </p>

    <dl class="platform-app-placeholder_meta">
      <div>
        <dt>App key</dt>
        <dd>{{ appKey }}</dd>
      </div>
      <div>
        <dt>Route prefix</dt>
        <dd>{{ routePrefix || 'Not configured' }}</dd>
      </div>
    </dl>
  </section>
</template>

<script setup lang="ts">
defineProps<{
  appKey: string
  appName: string
  routePrefix?: string
  status: string
  message: string
}>()
</script>

<style scoped>
.platform-app-placeholder {
  min-height: 100%;
  padding: 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 16px;
  color: #334155;
}

.platform-app-placeholder_header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.platform-app-placeholder_kicker {
  margin: 0 0 4px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  color: #64748b;
  text-transform: uppercase;
}

.platform-app-placeholder_title {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  color: #0f172a;
}

.platform-app-placeholder_status {
  flex-shrink: 0;
  padding: 4px 10px;
  border-radius: 999px;
  background: #eff6ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
}

.platform-app-placeholder_message {
  margin: 0;
  max-width: 760px;
  font-size: 14px;
  line-height: 1.7;
  color: #475569;
}

.platform-app-placeholder_meta {
  margin: 0;
  display: grid;
  gap: 10px;
  max-width: 760px;
}

.platform-app-placeholder_meta div {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 12px;
  padding: 10px 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #f8fafc;
}

.platform-app-placeholder_meta dt {
  font-size: 12px;
  font-weight: 700;
  color: #64748b;
}

.platform-app-placeholder_meta dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
  font-size: 12px;
  color: #0f172a;
}
</style>
