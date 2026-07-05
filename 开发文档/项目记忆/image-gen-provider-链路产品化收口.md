---
name: "image-gen Provider 链路产品化收口"
type: "task"
tags: [image-gen, provider, placeholder, sandbox, frontend, commit:93aded13]
agent: "codex"
created: "2026-07-05T08:10:27.387166+00:00"
---

2026-07-05 Codex 完成 image-gen 独立产品化与 Provider 链路收口，提交 93aded13。改动仅在 modules/image-gen/：list_templates 增加 configured/can_generate/fallback/prompt_language/cost_tracking；generate/history 增加 request_id/provider/file_ids/status/degraded_reason；placeholder 明确 status=degraded 且不是假成功；前端增加 provider 状态、降级提示、历史列表和预览；sandbox 覆盖模板、参数校验、缺凭据降级、placeholder 和记录 shape。验证：ruff check modules/image-gen 通过；pytest modules/image-gen/sandbox/test_module.py 9 passed；npm --prefix frontend run build 通过；call_capability(list_templates/generate/usage_history) placeholder 安全路径通过；未真实调用外部 provider，测试数据已清理。
