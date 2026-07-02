---
name: "capability-contract-r2节点4-收工验收报告"
type: "task"
tags: [capability-contract, verification, desktop-tools, 20260703]
agent: "capability-contract-worker-r2"
created: "2026-07-02T16:22:54.662277+00:00"
---

任务完成：活系统验证 manifest public_actions、register_capability、/api/modules/call 三者一致性，重点模块 knowledge、agent、memory、image-gen、scheduler、terminal-tools、desktop-tools。发现并处理两点：1) 初次活系统缺 knowledge:classify_pipeline_debt，但磁盘代码与静态契约均存在，重启后 /api/modules/capabilities 出现该能力，判定为后端进程未加载当前代码；2) desktop-tools:list_apps 经 /api/modules/call 返回 500，日志为 AttributeError: App object has no attribute backend_config，修复为读取 App.public_actions，并新增 backend/tests/test_module_boundary_contracts.py 断言禁止回归。最终验证：/api/health status ok；7 模块 manifest/live registry 精确比对：knowledge 12/12、agent 27/27、memory 16/16、image-gen 3/3、scheduler 3/3、terminal-tools 8/8、desktop-tools 15/15，missing_live/missing_manifest/role_mismatch 全空；call_capability 代表链路 knowledge classify_pipeline_debt、agent get_my_profile、memory list、image-gen list_templates、scheduler list、terminal-tools list_workspace、desktop-tools list_apps 均 200；desktop-tools sandbox PASS；ruff modules/desktop-tools/backend/router.py 与 backend/tests/test_module_boundary_contracts.py 通过；pytest backend/tests/test_module_boundary_contracts.py backend/tests/test_module_capability_drift.py 共 9 passed。改动文件：modules/desktop-tools/backend/router.py、backend/tests/test_module_boundary_contracts.py。未提交 commit。注意：工作区还有大量并行变更，非本 agent 所改；历史 task_queue failed=899 是既有债务。
