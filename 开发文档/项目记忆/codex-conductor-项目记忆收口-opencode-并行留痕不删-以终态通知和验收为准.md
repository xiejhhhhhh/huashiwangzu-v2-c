---
name: "codex-conductor 项目记忆收口：OpenCode 并行留痕不删，以终态通知和验收为准"
type: "task"
tags: [project-memory, cleanup, opencode, dev-toolkit, closeout]
agent: "codex-conductor"
created: "2026-07-03T05:34:32.183748+00:00"
---

2026-07-03 收口审查 `开发文档/项目记忆/` 本轮 OpenCode/Codex 并行新增记忆。结论：这些文件多数由 `memory_write` 或 `mcp_feedback` 生成，属于项目记忆唯一位置的正式留痕，不按“临时任务文档完成后删除”处理。早期 `mcp派发连通性测试-只读-完成`、`opencode网关55891与MCP派发工具升级`、`opencode-官方-sdk-主控制通路接入`、`opencode-mcp-sdk-后台队列调用补强`、`opencode-mcp-后台-job-终态通知收件箱` 是控制面/工具链演进记录，不等同于产品修复完成证明。

发现的重复形态：任务记忆与 `工具台反馈-*` 成对出现、部分任务有“初版记录 + 后续补强记录”（如前端 runtime openApp / KNOWN_VARIANTS），但这是 AGENTS 要求的归因与反馈链路，不直接删除。后续阅读口径：以带具体验证结果的最终任务记忆、`opencode_sdk_job_notifications` 终态通知、主线程验收和 `git diff --name-only` 边界为准；早期派发/连通性记录只说明任务/工具链曾启动或打通。

本次未删除任何项目记忆，未修改 backend/frontend/modules。`dev_toolkit/README.md` 已包含 OpenCode 固定 55891 网关、SDK 同步通路、SDK 后台队列、job notifications 收件箱和 PTY/CLI 兜底说明，暂不再扩大改写。残留风险：当前工作区仍有大量其他 worker 的产品代码 dirty/untracked，本次仅审查文档边界，不判断那些产品改动的正确性。
