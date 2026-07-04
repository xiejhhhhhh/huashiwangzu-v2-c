---
name: "Knowledge Content Agent 引用与 IR 权威归一收口"
type: "task"
tags: [knowledge, content-ir, agent, evidence, artifact, architecture, release-gate]
agent: "codex"
created: "2026-07-04T13:40:46.826291+00:00"
---

# 改了什么

完成 Knowledge / ContentPackage / Content IR / Agent references / artifacts 权威归一收口：Content IR 增补并持久化 `source_file_id/source_module/parser/assets/resources/metadata/warnings/quality`；Artifact publish 回包统一 `artifact_id/package_id/source_file_id/origin_module/download_url/open_url`；Agent evidence 只保存轻量引用并保留 Knowledge result 的 `file_id/document_id/chunk_id/package_id/page/section/score` 等字段；Knowledge 搜索结果与 Agent evidence 使用同一字段语义，前端支持打开、下载、复制引用、metadata 查看，无法打开时给明确原因。

# 权威边界

Content IR / ContentPackage 是内容结构权威；Knowledge 是 document/chunk/page fusion/profile/relation 的检索与知识权威；Artifact 是文件化产物权威；Agent 只保存引用，不复制 Knowledge chunk、Content IR、Artifact 全量 metadata。跨模块仍通过 framework capability / Content / Artifact / File API 回源，未新增模块间 import 或直接读表。

# 验证了什么

ruff changed Python files PASS；`backend/tests/test_content_artifact_publish.py` 8 passed；`backend/tests/test_content_ir_architecture.py` 58 passed；Agent workflow service 13 passed；Agent workflow API 7 passed；Knowledge sandbox 15 passed；Knowledge backend tests 61 passed；`npm --prefix frontend run build` PASS；`/api/health` ok；`release_gate(skip_ui=true, mode=preflight)` PASS_WITH_DEBT，blockers=[]，release_safe/deploy_allowed=true；`git diff --check` on core files PASS。

# 交付文档

新增 `开发文档/项目记忆/KnowledgeContentAgent引用与IR权威归一总收口.md`，记录最终权威结构、避免的重复结构、跨模块边界、修改文件、验证命令、release_gate 结果和剩余 debt。

# 残留风险

工作区已有大量其他任务 dirty/untracked 文件，本任务未回滚、不归因；release_gate debt 主要来自 dirty worktree 与 skip-ui/preflight 未覆盖完整 UI smoke/sandbox/model-fallback。无 blocker。

# 关联 commit

未提交。
