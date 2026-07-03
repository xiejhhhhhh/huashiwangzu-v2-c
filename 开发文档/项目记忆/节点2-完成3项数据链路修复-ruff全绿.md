---
name: "节点2-完成3项数据链路修复+ruff全绿"
type: "task"
tags: [knowledge, fixes, parse-status, entity-chain, transaction-safety]
agent: "opencode-r3-knowledge-memory"
created: "2026-07-03T05:12:54.950388+00:00"
---

已完成三项数据链路修复：

修复A: to_legacy_dict 现在输出 parse_status + resource_diagnostics（ir_models.py）
修复B: parse_and_index_document 现在捕获 DocumentIr.parse_status 并传播到 KbDocument 状态（而非强制"done"），同时在 API 响应中暴露 ir_parse_status 和 ir_resource_diagnostics（document_service.py）
修复C: entity_service 移除了中间的 `await db.commit()`（之前删除旧数据后就提交，若后半段崩溃则数据永久丢失），改为让同事务的最终 commit 做原子写

ruff 全部 8 个文件通过。

下一步：运行后端 pytest 验证不破坏现有测试。
