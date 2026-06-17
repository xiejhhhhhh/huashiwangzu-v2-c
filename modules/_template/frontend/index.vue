<template>
  <section class="module-entry">
    <p class="module-entry__kicker">Module template</p>
    <h2 class="module-entry__title">MODULE_DISPLAY_NAME</h2>
    <p class="module-entry__message">
      This is the starter entry for a new module. Replace it with your module UI after copying the template.
    </p>
  </section>
</template>

<script setup lang="ts">
// Keep this file self-contained so copied modules stay physically isolated.
</script>

<style scoped>
.module-entry {
  min-height: 100%;
  padding: 24px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  gap: 12px;
  color: #1f2937;
}

.module-entry__kicker {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0;
  text-transform: uppercase;
  color: #64748b;
}

.module-entry__title {
  margin: 0;
  font-size: 22px;
  line-height: 1.2;
  color: #0f172a;
}

.module-entry__message {
  margin: 0;
  max-width: 720px;
  font-size: 14px;
  line-height: 1.7;
  color: #475569;
}
</style>
