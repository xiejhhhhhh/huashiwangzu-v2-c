---
name: "CleanReleaseDebt 队列归档与 Sandbox warning 降噪收口"
type: "task"
tags: [release-gate, task-queue, sandbox-matrix, clean-release]
agent: "codex"
created: "2026-07-05T07:56:51.517163+00:00"
---

- 队列治理增加非 dry-run 安全守卫：必须传 task_ids 或 confirm_all_failed=true；router 层返回统一错误，service 层也 fail-closed。
- 真实归档 deleted-source obsolete failed tasks：初始 6 条（6819, 6858, 6885, 6891, 6893, 6906）已 processed=6；full gate 后新增 2 条（8012, 8006）也已按 task_ids processed=2；最终 audit failed=0。
- Sandbox chunk warning 口径改为 INFO：构建成功但 Vite chunk-size warning 不计 clean-release debt；失败构建仍为 BLOCKER。
- 已提交本任务代码：cb1b1caa fix: close clean release debt gates。

治理前：failed=6；5 条 recent deleted-source obsolete，1 条 historical debt，均为 kb_pipeline / Invalid or unsupported image content / doc_deleted + no_file_row。
首次归档后：failed=0，historical_failed_debt_count=0，deleted_source_obsolete_failed_count=0。
full gate 新增：8012、8006 两条 deleted-source obsolete；二次归档后最终 audit failed=0、pending=0、running=0、completed=578。
Sandbox warning：19 个模块均为 Vite chunk-size warning（agent, desktop-tools, doc-viewer, docx-parser, douyin-delivery, excel-engine, hello-world, image-viewer, image-vision, knowledge, pdf-parser, pdf-viewer, ppt-viewer, pptx-parser, terminal-tools, text-editor, text-parser, wechat-writer, xlsx-parser），已归类 INFO。

提交：cb1b1caa。
