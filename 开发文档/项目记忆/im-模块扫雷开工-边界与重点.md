---
name: "IM 模块扫雷开工：边界与重点"
type: "task"
tags: [im, sweep, start, boundary]
agent: "codex-im-sweep-20260703-r2"
created: "2026-07-03T07:23:00.329809+00:00"
---

任务开始：对 modules/im 做模块级扫雷和必要修复。写入范围限定 modules/im/** 与 开发文档/项目记忆/**；不修改 backend/app、frontend/src、其他模块、data/uploads。重点检查统一响应语义、假成功/空实现、权限/owner 隔离、跨模块边界、框架表读写风险、分页参数上限、manifest/runtime/router 声明一致性、sandbox 是否真测。
