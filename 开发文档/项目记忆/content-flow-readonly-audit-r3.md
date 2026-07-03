---
name: "Content flow readonly audit r3"
type: "task"
tags: [content, artifact, permissions, readonly-audit, r3]
agent: "content-flow-readonly-audit-r3"
created: "2026-07-03T10:07:06.431341+00:00"
---

# content-flow-readonly-audit-r3

只读审计 Content Package / content router / export_service / artifact_service 链路；未修改产品代码，未触碰 data/uploads，未提交。为避免污染数据，没有调用会触发 lazy parse/publish/export 的写入型能力。

## 证据范围
- 入口：AGENTS.md、开发文档/README.md。
- 工具台：brief、plan_task、worktree_guard、code_explore、code_node、code_impact、routes、capabilities、db_schema、db_reverse_audit、probe、tail_log、finish_task。
- 关键文件：backend/app/routers/content.py、backend/app/services/content/export_service.py、backend/app/services/content/package_service.py、backend/app/services/content/pipeline_service.py、backend/app/services/artifact_service.py、backend/app/services/file_reader.py、backend/app/services/uploaded_file_runner.py、backend/app/schemas/content_package.py、backend/tests/test_content_ir_architecture.py、modules/office-gen/runtime/index.ts、modules/desktop-tools/backend/router.py、modules/office-gen/backend/router.py。
- 表：framework_content_packages、framework_content_package_versions、framework_artifacts、framework_artifact_versions、framework_artifact_operations、framework_resources、framework_resource_refs。

## 发现
1. P1: content publish 的 target_file_id 被静默忽略。
   - REST /api/content/packages/{package_id}/publish 和 content:publish capability 都接收 target_file_id；modules/office-gen/runtime/index.ts 也发送 target_file_id。
   - backend/app/services/content/export_service.py ContentExportService.publish(target_file_id=...) 没使用该参数，而是 export 新文件后 create_artifact(file_id=new_file_id)。
   - artifact_service.publish_artifact 已有 target_file_id 替换语义，但 content publish 没复用。
   - 建议：ContentExportService.publish 在 target_file_id 存在时先校验 package 访问和目标写权限，然后走 artifact_service.publish_artifact 或 replace_file_content 路径；返回必须包含 replaced/target_file_id 状态。
   - 测试：content publish with target_file_id 应替换目标文件、不新增意外目标文件；无权限 target_file_id 失败；未传 target_file_id 保持创建新 artifact/file 语义。

2. P1/P2: content:get_file_content 仍存在 success true + empty blocks 的假成功分支，并且 advertised read-only 但可能触发 pipeline 写入。
   - backend/app/routers/content.py _cap_get_file_content 在 pipeline_result 后仍找不到 consumable package 时返回 success true, source none, blocks [], status not_parsed。
   - /api/modules/call 只会把 success:false 转 422；success:true 会让上游只能自行理解 status/blocks，Agent orchestrator 还把 content__get_file_content 注册成 read-only/concurrency_safe。
   - 现有测试覆盖 parser exception 和 failed status，但没有覆盖 skipped/not_parsed/empty blocks fail-closed。
   - 额外细节：无 ContentPackage 时，当前代码 pkg_svc.get_package 会抛 NotFound，实际不会 lazy get_or_create；注释和行为不一致。
   - 建议：把 not_parsed/empty consumable result 改成 success:false 或明确 needs_download/parse_unavailable 状态；若保留 lazy parse，工具元数据不能标 read-only，或拆 read-only get 与 write lazy_parse。
   - 测试：mock pipeline 返回 skipped/ok-but-no-package，断言 content:get_file_content 不返回 success true + empty blocks；无包场景行为与文档一致。

3. P1: ContentPipelineService.run_pipeline 在 get_or_create 前用 file_record.owner_id 做 access check，caller 未先授权。
   - backend/app/services/content/pipeline_service.py run_pipeline 读取 File 后调用 pkg_svc.get_or_create(db, file_id, file_record.owner_id, caller)。
   - package_service.get_or_create 会 check_file_access(db, file_id, owner_id)，这里 owner_id 是文件 owner，天然通过；因此非授权 caller 可能先创建/污染他人 ContentPackage，再由 parser 的 uploaded_file_runner/read_uploaded_file 失败拦截内容读取。
   - 解析器主路径（pdf/docx/xlsx/text/image 等）使用 run_uploaded_file_capability -> read_uploaded_file -> check_file_access，未确认直接内容泄露；问题主要是 pipeline 前置写入/状态污染和权限边界不一致。
   - 建议：run_pipeline 先 resolve_caller_user_id(caller) 并 check_file_access(db, file_id, caller_user_id)；创建包 owner 可仍用 file_record.owner_id；写类 pipeline 对 read share/edit share的策略需产品确认。
   - 测试：无 share 的 user 调 content:pipeline(file_id=others) 不创建 framework_content_packages；read share 是否允许 parse 生成 owner-owned package需明确；edit share 写入状态需覆盖。

## 正向确认
- package_service.get_package/get_full/list_blocks/list_resources/get_resource 基本通过 owner 或 source_file_id 的 check_file_access 控制。
- content:store_resource / store_analysis_resource 在带 file_id 时先 check_file_access 后存 Resource。
- artifact_service.publish_artifact/replace_file_from_artifact 最终替换内容时 replace_file_content 会调用 check_file_write_access；read share 不应能写。
- parser 文件读取主路径统一 run_uploaded_file_capability -> read_uploaded_file -> check_file_access + path traversal guard。

## 工作区说明
finish_task/git 视图显示已有 7 个 dirty/untracked 项（含 backend/app/services/content/export_service.py 等），不是本审计产生；本审计未改产品代码。关联 commit：无。
