---
name: "Lane C Content Artifact Parser IR 只读审计"
type: "task"
tags: [content, artifact, parser-ir, readonly-audit, lane-c]
agent: "codex-lane-c-content-artifact-parser-ir-audit"
created: "2026-07-04T12:56:39.345506+00:00"
---

# 做了什么

只读审计 Lane C Content/Artifact/Parser IR：读取 AGENTS 与开发文档入口，使用 brief/plan_task/worktree_guard、CodeGraph/code_node/code_impact、routes/capabilities/db_schema、health probe 与 content:validate_ir 探针，检查 backend/app/services/content、backend/app/routers/content.py、Artifact publish、parser modules manifest/README/sandbox。

# 关键结论

- ContentPackage 解析状态与 publish 状态机已基本落地：pending/parsed/degraded/failed/archived 与 draft_package/compiled_preview/published_artifact/file 分离。
- publish 无 target 会导出物理 file 并创建 Artifact；publish 到 target 会 check_file_write_access、替换目标文件并追加 ArtifactVersion/Operation。
- ContentPackage/Resource 读取与写入路径大多走 check_file_access/check_file_write_access；write_ir 对 source_file_id 的共享文件写入要求 edit share。
- Content IR validator/normalizer/write_ir 已注册为 content:* 能力，活栈验证英文 paragraph 通过、旧式中文 block type 表格 被拒绝。
- 主要缺口：parser pipeline 仍直接保存 parser 返回的 legacy blocks，未统一转换/校验到 Content IR；csv-parser 输出中文 block type，image-vision 输出 metadata block，部分 parser README/sandbox 文档矩阵仍需补齐或对齐。

# 验证了什么

- /api/health 返回 ok。
- content:validate_ir 对合法 document IR 返回 valid=true。
- content:validate_ir 对 block type=表格 返回 unsupported_block_type，证明 parser legacy blocks 与新 IR schema 存在漂移。
- git 检查发现开工后出现并发 dirty README/manifest/项目记忆变更；本审计未修改产品源码。

# 残留风险

没有执行 parser sandbox 或 publish 写入流，避免审计任务产生业务数据/文件副作用；建议后续按报告中的验证命令跑针对性测试。

# 关联 commit

无，本次只读审计未提交。
