---
name: "审计修复-P0-Parser资源诊断必须贯通ContentPackage和知识库消费者"
type: task
tags: ["审计修复", "P0", "parser", "resource_diagnostics", "ContentPackage", "DcoumentIr", "parse_status"]
created: 2026-07-03
agent: opencode
---

代理: opencode

修复 3 个断链点，将 parser resource_diagnostics 贯通到两个消费侧:

1. DocumentIr 新增 `parse_status`(ok/degraded/failed) 和 `resource_diagnostics` 字段 + `from_legacy_blocks` 新增参数（优先 stored_resource_id）
2. knowledge parse_document 提取 resource_diagnostics 并计算 parse_status 降级
3. ContentPackage run_pipeline 从硬编码 "parsed" 改为 parse_status 动态值（资源失败→degraded）

改动: modules/knowledge/backend/ir_models.py, modules/knowledge/backend/services/parsing_service.py, backend/app/services/content/package_service.py, backend/tests/test_parser_resource_diagnostics.py

验证: pytest 17+46=63 passed, ruff all checks passed, health ok
