---
name: "knowledge-schema-review-r3节点2-raw单测旧路径与真实DB依赖修复"
type: "gotcha"
tags: [knowledge, test, raw-collection, gotcha, 20260703]
agent: "knowledge-schema-review-r3"
created: "2026-07-02T16:41:01.533692+00:00"
---

复验 `modules/knowledge/tests/test_raw_collection.py` 时发现测试仍 import 旧路径 `modules.knowledge.backend.raw_collection_service`，且导入新 service 后会通过 `AsyncSessionLocal` 触发真实 DB 清理旧 raw 记录。已在模块边界内小修：导入改为 `modules.knowledge.backend.services.raw_collection_service`，并用 fake `AsyncSessionLocal` 让测试保持纯单元、不依赖真实 `kb_raw_data` 表。验证：相关 17 个 pytest 通过，ruff 对该测试通过。
