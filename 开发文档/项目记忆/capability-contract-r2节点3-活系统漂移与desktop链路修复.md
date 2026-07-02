---
name: "capability-contract-r2节点3-活系统漂移与desktop链路修复"
type: "task"
tags: [capability-contract, desktop-tools, knowledge, live-system, 20260703]
agent: "capability-contract-worker-r2"
created: "2026-07-02T16:21:15.384514+00:00"
---

证据：7 模块 manifest/public_actions 与磁盘 register_capability 静态测试通过，但活系统初次 /api/modules/capabilities 缺 knowledge:classify_pipeline_debt；重启后该能力出现，判定为后端进程未加载当前磁盘版本。随后 call_capability 验证重点模块时发现 desktop-tools:list_apps 500，日志显示 AttributeError: App has no attribute backend_config。修复：modules/desktop-tools/backend/router.py 改为读取当前 App.public_actions，并清理同文件 ruff 点名的安全 lint；backend/tests/test_module_boundary_contracts.py 增加防止 app.backend_config 回归的断言。验证：ruff desktop-tools router 和测试文件通过；backend/tests/test_module_boundary_contracts.py + test_module_capability_drift.py 共 9 passed。
