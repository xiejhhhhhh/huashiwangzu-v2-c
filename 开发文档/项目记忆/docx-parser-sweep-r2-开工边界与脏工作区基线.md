---
name: "docx-parser sweep r2 开工边界与脏工作区基线"
type: "task"
tags: [docx-parser, module-sweep, r2, boundary, task_id:docx-parser-sweep-20260703-r2]
agent: "codex-docx-parser-sweep-20260703-r2"
created: "2026-07-03T07:37:40.747313+00:00"
---

任务：对 modules/docx-parser 做模块级扫雷和必要修复。已读 开发文档/README.md 与 开发文档/03_模块开发文档/README.md；项目工具台 plan_task/worktree_guard/routes/capabilities 已调用。边界：只写 modules/docx-parser/** 与 开发文档/项目记忆/**。基线：worktree_guard 发现已有 64 个未提交条目，主要在 data/uploads、desktop-tools、docs-open、im、wechat-writer 和项目记忆；这些视为他人并发改动，本任务不触碰、不 revert。docx-parser 当前公开能力为 parse(file_id:int)，min_role viewer；路由有 /api/docx-parser/health 与 /api/docx-parser/parse。下一步用 codegraph/工具台查影响面并实读模块关键文件。
