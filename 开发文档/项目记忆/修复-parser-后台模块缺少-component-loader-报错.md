---
name: "修复 parser 后台模块缺少 component loader 报错"
type: task
tags: ["desktop", "app-registry", "manifest", "parser", "component-loader"]
created: 2026-06-28
agent: zcode
---

# 改了什么
- 修复桌面启动时 `Missing component loader for markdown-parser/csv-parser/structured-parser/email-parser: <empty>` 控制台报错。
- 根因：这四个 parser 是无前端 UI 的后台能力模块，`component_key` 为空，但 manifest 中 `window_type` 仍是 `normal`，前端注册表按普通窗口应用找组件，空 key 找不到 loader 就报错。
- 将四个 parser manifest 的 `window_type` 改为 `background-service`。
- `frontend/src/desktop/app-registry/app-loader.ts` 增加兜底：只要 `entry_component_key` 为空，就使用后台服务空组件占位，不再报 Missing loader。
- 触发 `POST /api/app-manager/apps/scan-register` 同步注册表，确认数据库中四个 parser 均为 `background-service`。

# 验证了什么
- `cd frontend && npm run build`：通过。
- `/api/app-manager/apps/scan-register`：updated 33。
- SQL 查询 `framework_app_registry` 确认 `csv-parser/email-parser/markdown-parser/structured-parser` 的 `window_type=background-service` 且 `component_key=''`。

# 残留风险
- 若其他模块未来声明 `component_key=''` 但仍想打开窗口，前端会按后台服务静默处理；这符合当前约定：无组件 key 即无前端窗口。
