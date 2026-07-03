---
name: "frontend/runtime contract drift readonly audit r3"
type: "task"
tags: [frontend, runtime, contract, audit, public_actions, typescript, r3]
agent: "frontend-runtime-contract-audit-r3"
created: "2026-07-03T10:38:24.088763+00:00"
---

只读审计 frontend/src 与 modules/*/runtime/index.ts 的前后端契约漂移，未修改产品代码、不提交。已读 AGENTS.md、开发文档/README.md、框架/模块文档，使用 brief/plan_task/worktree_guard/code_explore/capabilities/routes/tail_log。结论：P0 无。审计范围内未发现 any/as any/@ts-ignore/@ts-expect-error/转中文( 字段名误用；标准 modules/*/runtime/index.ts 的 modules.call 均使用 /api/modules/call + target_module/action/parameters，与 backend/app/routers/modules.py 的 ModuleCallRequest 对齐。发现 P1：manifest public_actions 与后端 register_capability 参数清单存在元数据漂移，动作均存在但能力发现会漏可选/实际参数，重点 excel-engine 多个动作缺 sheet/start_row/start_col/folder_id/target_file_id/state_key 等，office-gen 缺 content_ir/folder_id 以及将 content/sheets/slides、blocks/content_ir 写成斜杠伪字段，agent 若干能力缺 max_rounds/gates/gate_retry/allowed_tools/focus_areas/attributes/tags/session_id 等，codemap report_inaccuracy 缺 codemap_said/actual/reason，image-gen usage_history 缺 limit。P2：modules/media-intelligence/runtime/index.ts 是 96 行定制轻量 runtime，仅暴露 settings/modules，缺模板 runtime 的 auth/files/office/gateway/tasks/notifications/logs 等平台命名空间；当前自身前端只用 modules.call，能跑，但作为 modules/*/runtime/index.ts 契约不完整。P2：doc-viewer/ppt-viewer/pdf-viewer 前端仍直接 apiPost('/modules/call', {target_module, action, parameters})，字段正确但绕过 platform.modules.call 封装，后续应收口到 runtime SDK 以减少漂移面。修复边界建议：只改对应模块 manifest/runtime/frontend，避免触碰 backend/content/knowledge/agent 当前他人工作区；若要以注册表为真源，应由模块内同步 public_actions 元数据或做生成校验，不改框架。
