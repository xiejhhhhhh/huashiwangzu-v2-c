<template>
  <section class="terminal-tools-entry">
    <div class="terminal-tools-status">
      <el-icon :size="48" color="#409eff"><Monitor /></el-icon>
      <h2>终端工具</h2>
      <p class="terminal-tools-desc">
        为 Agent 提供受边界约束的终端执行能力。所有命令在用户独立工作区内运行，
        成果经 publish 显式交付到桌面文件系统。
      </p>
      <el-divider />
      <div class="terminal-tools-caps">
        <h3>已注册能力</h3>
        <el-tag v-for="cap in capabilities" :key="cap" type="info" effect="plain" style="margin: 4px;">
          {{ cap }}
        </el-tag>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Monitor } from '@element-plus/icons-vue'

const capabilities = ref([
  'terminal-tools:exec',
  'terminal-tools:write_file',
  'terminal-tools:read_file',
  'terminal-tools:list_workspace',
  'terminal-tools:publish',
  'terminal-tools:import',
])
</script>

<style scoped>
.terminal-tools-entry {
  min-height: 100%;
  padding: 32px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
}
.terminal-tools-status {
  text-align: center;
  max-width: 560px;
}
.terminal-tools-desc {
  color: #64748b;
  font-size: 14px;
  line-height: 1.7;
  margin: 12px 0 0;
}
.terminal-tools-caps {
  text-align: left;
}
.terminal-tools-caps h3 {
  font-size: 14px;
  color: #0f172a;
  margin: 0 0 8px;
}
</style>
