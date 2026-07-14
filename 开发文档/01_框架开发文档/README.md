# 框架开发文档

## 前端架构

Vue 3 + TypeScript + Element Plus + Vite。模拟桌面环境。

### 核心层

- `frontend/src/platform/` — 登录、桌面、窗口管理、任务栏、启动器
- `frontend/src/shared/` — 通用 API 封装、事件总线、类型
- `frontend/src/app-entry/` — 应用入口、路由

### 模块加载

1. 构建时 `scripts/scan-modules.js` 扫描 `modules/*/manifest.json`
2. 生成模块注册表 → 桌面壳按 manifest 配置加载组件
3. 模块前端入口：`modules/{key}/frontend/index.vue`
4. 模块运行时 API：`modules/{key}/runtime/index.ts`（提供 auth/files/gateway 等能力）

### 窗口系统

- 窗口状态用 Pinia store 管理
- 支持：普通窗口、最大化、最小化到任务栏、多窗口
- manifest 里配 `default_width/height`、`singleton`、`allow_multiple`

## 改动边界

框架改动只动 `frontend/src/` 和 `backend/app/`，不动 `modules/`。
