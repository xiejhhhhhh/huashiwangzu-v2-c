# 迁移为 ai-assistant 模块

# AI 助手模块迁移

## 当前发现

- AI 助手后端代码仍在 `backend/app/services/agent/`，不是模块目录。
- AI 助手前端仍通过 `frontend/src/desktop/app-registry/component-key-map.generated.ts` 加载（路径 `@应用模块/AI助手/frontend/index.vue`）。
- 没有 `modules/ai-assistant/manifest.json` 来让桌面壳通过模块扫描发现 AI 助手。
- 没有 `sandbox/`，无法在桌面壳外独立测试 AI 助手。

## 目标

- 创建 `modules/ai-assistant/`。
- 建立 `manifest.json`、`runtime.config.json`、`runtime/`、`frontend/`、`backend/`、`sandbox/`、`tests/`。
- AI 助手先通过 sandbox 独立运行和验收，再接入桌面壳。

## 验收

- sandbox 中可以创建会话、发送消息、接收流式回复。
- 主桌面壳可以通过模块 manifest 打开 AI 助手。

## 完成后归档

完成后把当前 AI 助手模块结构合并回本目录 `README.md`，再删除本文件。
