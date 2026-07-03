---
name: "image-gen records 空表链路验证稳定节点2"
type: "task"
tags: [image-gen, imagegen_records, ledger, r3, stable-node]
agent: "codex-douyin-codemap-imagegen-flow-audit-r3"
created: "2026-07-03T11:11:30.633990+00:00"
---

# 改了什么
未修改 image-gen 代码。基于上一轮审计的 imagegen_records=0 疑点，执行低成本 placeholder 活栈验证，确认当前代码的记录链路可达。

# 验证了什么
- 活栈：POST /api/image-gen/generate 使用 template=placeholder、prompt=r3-imagegen-ledger-*，返回 file_id=3093、placeholder=true。
- 活栈：GET /api/image-gen/history 立即读到 imagegen_records id=4，status=placeholder，image_count=1。
- 清理：删除本次 imagegen_records id=4、framework_file_items id=3093 及对应物理文件，未保留测试数据。
- sandbox：backend/.venv/bin/python -m pytest modules/image-gen/sandbox/test_module.py -q -> 6 passed.
- ruff：cd backend && .venv/bin/ruff check ../modules/image-gen/backend ../modules/image-gen/sandbox/test_module.py -> All checks passed.

# 是否还有残留风险
当前结论：imagegen_records=0 不是当前源码写入断链，而是当前库没有保留历史生成记录；历史“Liblib 实测成本落库”仍缺当前库可复核历史数据。真实 Liblib/GPTStore 成本字段仍需带预算单独验证。

# 关联 commit
无。
