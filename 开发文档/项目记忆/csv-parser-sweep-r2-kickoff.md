---
name: "csv-parser sweep r2 kickoff"
type: "task"
tags: [csv-parser, sweep, kickoff]
agent: "codex-csv-parser-sweep-20260703-r2"
created: "2026-07-03T07:45:36.365520+00:00"
---

开始 modules/csv-parser 模块级扫雷。约束：只写 modules/csv-parser/** 与 开发文档/项目记忆/**；重点检查 file_id 权限通路、统一响应、CSV 编码/分隔符/空表/大表、失败不可假成功、sandbox 真实样例、manifest/backend capability 一致。已先读 开发文档/README.md 和 开发文档/03_模块开发文档/README.md。
