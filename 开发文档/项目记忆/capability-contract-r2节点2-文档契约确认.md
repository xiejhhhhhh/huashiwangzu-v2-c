---
name: "capability-contract-r2节点2-文档契约确认"
type: "task"
tags: [capability-contract, docs, manifest, registry, 20260703]
agent: "capability-contract-worker-r2"
created: "2026-07-02T16:14:43.238665+00:00"
---

已读 开发文档/README.md、01_框架开发文档、02_底层开发文档、03_模块开发文档，以及重点模块 README（knowledge/agent/memory/image-gen/scheduler/terminal-tools/desktop-tools）。确认契约事实：后端跨模块调用唯一通路是 module_registry + /api/modules/call；运行时以 register_capability 为准，manifest public_actions 为声明元数据，需与注册能力同步；/api/modules/call 入参字段为 parameters。README 暴露的重点能力数：knowledge 8、memory README 写 9+3 experience、image-gen 3、scheduler 3、terminal-tools 8、desktop-tools 4；agent README 表述 20+ 公共能力，需以 manifest/registry 实测为准。
