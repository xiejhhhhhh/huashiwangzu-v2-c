<template>
  <section class="terminal-tools-entry">
    <div class="terminal-tools-status">
      <span class="terminal-icon">🖥️</span>
      <h2>终端工具</h2>
      <p class="terminal-tools-desc">
        为 Agent 提供受边界约束的终端执行能力。所有命令在用户独立工作区内运行，
        成果经 publish 显式交付到桌面文件系统。
      </p>
      <hr class="terminal-divider" />
      <div class="terminal-tools-caps">
        <h3>已注册能力</h3>
        <span v-for="cap in capabilities" :key="cap" class="terminal-cap-tag">{{ cap }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const capabilities = ref([
  'terminal-tools:exec',
  'terminal-tools:write_file',
  'terminal-tools:read_file',
  'terminal-tools:list_workspace',
  'terminal-tools:publish',
  'terminal-tools:import',
  'terminal-tools:run_python',
  'terminal-tools:chart',
])
</script>

<style scoped>
.terminal-tools-entry {
  min-height: 100%;
  padding: 32px;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: #fff;
}

.terminal-tools-status {
  text-align: center;
  max-width: 500px;
}

.terminal-icon {
  font-size: 48px;
  display: block;
  margin-bottom: 16px;
}

.terminal-tools-status h2 {
  margin: 0 0 8px;
  font-size: 22px;
  font-weight: 600;
  color: #303133;
}

.terminal-tools-desc {
  margin: 0;
  font-size: 14px;
  color: #909399;
  line-height: 1.5;
}

.terminal-divider {
  border: none;
  border-top: 1px solid #e4e7ed;
  margin: 20px 0;
}

.terminal-tools-caps h3 {
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 500;
  color: #606266;
}

.terminal-cap-tag {
  display: inline-block;
  margin: 4px;
  padding: 2px 10px;
  font-size: 12px;
  color: #909399;
  background: #f4f4f5;
  border: 1px solid #e9e9eb;
  border-radius: 4px;
  font-family: monospace;
}
</style>
