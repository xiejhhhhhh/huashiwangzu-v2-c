---
name: "目标: call_capability 需用 target_module 字段名"
type: gotcha
tags: ["api", "module-call", "gotcha"]
created: 2026-06-23
---

现象: /api/modules/call 用 module 字段报 422。根因: 框架期望 target_module 字段名
