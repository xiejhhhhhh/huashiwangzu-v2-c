---
name: "backend foundation degraded ContentPackage 与私有模块 capability 收口复核"
type: "task"
tags: [backend, foundation, content-package, private-modules, tests]
agent: "codex-backend-foundation-closure"
created: "2026-07-03T05:40:05.890599+00:00"
---

# 改了什么
- 复核 ContentPackage degraded 语义：当前相关代码已将 parsed/degraded 收敛为 consumable status，`content:get_file_content` 与文件下载 ContentPackage compile helper 不再只认 parsed。
- 补充消费链路测试：degraded package 能返回正文 blocks；download compile 会选择 degraded ContentPackage 并调用 content:compile。
- 复核 private_module_service：激活失败 import 后、tracking 前的 capability 会按 activation 前快照回滚；成功激活后 tracked capability 在 deactivate 时清理。
- 补充 private module lifecycle 测试：激活失败清 capability、停用清 tracked capability；同时把测试 owner_id 从写死 1 改为登录返回 user.id，避免环境种子 ID 漂移。
- private_modules HTTP 失败口径未擅自改动；当前测试要求 activation/rollback failure 走 HTTP 500，router 中 success:false 分支仍保留为风险观察点。

# 验证了什么
- ruff: content.py、file_transfer.py、package_service.py、private_module_service.py、test_content_ir_architecture.py、test_parser_resource_diagnostics.py、test_private_modules_lifecycle.py、test_agent_profile_evolve_soft_failure.py 全部通过。
- pytest: test_private_modules_lifecycle.py 5 passed；test_parser_resource_diagnostics.py 18 passed；test_content_ir_architecture.py 全文件 48 passed；TestContentFailureSemantics 精确目标 5 passed；test_agent_profile_evolve_soft_failure.py 3 passed；finish_task 组合目标 31 passed。
- probe /api/health 返回 status ok。

# 残留风险
- 工作区仍有大量并行 worker dirty/untracked 文件，本轮未回退别人的改动。
- /api/health 显示 task_queue failed=905，为存量历史债。
- private module 动态路由 failure 当前因回滚刷新再次抛错而表现为 HTTP 500；本轮按现有测试要求只复核风险，未擅自改为 HTTP 200 + success:false 或其他口径。

# 关联 commit
- 未提交。
