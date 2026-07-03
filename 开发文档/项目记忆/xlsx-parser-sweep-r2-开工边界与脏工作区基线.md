---
name: "xlsx-parser sweep r2：开工边界与脏工作区基线"
type: "task"
tags: [xlsx-parser, module-sweep, r2, boundary, task_id:xlsx-parser-sweep-20260703-r2]
agent: "codex-xlsx-parser-sweep-20260703-r2"
created: "2026-07-03T07:37:58.325992+00:00"
---

开工读取 开发文档/README.md 与 开发文档/03_模块开发文档/README.md。工具台 brief/plan_task/worktree_guard/code_explore 已执行。当前仓库存在 66 个既有未提交条目，主要在 data/uploads、desktop-tools、docs-open、im、wechat-writer 与项目记忆；本任务严格不碰这些既有改动。写入边界限定为 modules/xlsx-parser/** 与本任务项目记忆/反馈。扫雷重点：file_id 必须走 run_uploaded_file_capability/check_file_access；解析失败不得假成功；sandbox 必须真实样例解析；manifest public_actions 与 backend register_capability 对齐。
