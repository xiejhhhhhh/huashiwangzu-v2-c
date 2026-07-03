---
name: "opencode MCP SDK审计完成-最小可用但执行代理需隔离"
type: "task"
tags: [opencode, mcp, audit, r2, sdk, gateway, dirty-worktree, execution-agent-risk]
agent: "codex-opencode-mcp-audit-20260703-r2"
created: "2026-07-03T07:19:04.625546+00:00"
---

审计完成记录（codex-opencode-mcp-audit-20260703-r2）：

范围：只测试/审计 opencode MCP/SDK 可用性和风险，不改产品代码；允许写 开发文档/项目记忆/**。已读项目入口文档、框架开发文档、底层开发文档；已调用 brief、plan_task、worktree_guard。

工具可用性：
1. opencode_gateway_status 成功：listening=true，url=http://127.0.0.1:55891，pid=5166，opencode_version=1.17.13。
2. opencode_sdk_smoke 成功：session=ses_0d9292e52ffe3TJUyC0b70JwqQ，assistant text=OPENCODE_SDK_SMOKE_OK，provider=opencode-go，model=deepseek-v4-flash，cost=0.0032613，tokens.total=23261。
3. opencode_sdk_prompt：传 agent=codex-opencode-mcp-audit-20260703-r2 失败，UnknownError ref=err_e355308f；不传 agent 使用默认 build 成功，返回 dirty worktree attribution 风险判断，cost=0.0032711，tokens.total=23303。
4. 第二次默认只读 prompt 成功：assistant text=READ_ONLY_SECOND_OK，cost=0.00325892，tokens.total=23251，未出现 patch part。

风险证据：
1. gateway 日志明确提示 OPENCODE_SERVER_PASSWORD is not set; server is unsecured。作为执行代理前必须配置密码或只允许受控本地调用。
2. opencode_gateway_status 的 log_tail 会回显 JSON-RPC/turn metadata 片段（session_id/thread_id/turn_id/workspace/remote URL/commit hash/dirty 状态等），存在信息泄露和日志污染风险，应脱敏或截断。
3. 默认 opencode_sdk_prompt 第一次成功响应中 assistant parts 包含 patch part，文件为 /Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/modules/desktop-tools/sandbox/test_module.py。该文件本来已是脏工作区修改；即使 prompt 明确要求只读，也说明 SDK 会把工作区 snapshot/patch 与会话绑定，脏工作区下非常容易误判“某 agent 改了什么”。
4. 自定义 agent 参数失败且错误只给 UnknownError/ref，需要工具层校验 agent 枚举或返回更可读错误。
5. 当前分支同时有并行 worker 写入：状态从开工前约 96/98 条变化增长到最终 110 条，期间新增 modules/**、data/uploads/**、项目记忆等；因此本审计不能对并发期间新增产品改动作精确归因。我的可归因写入是本条及 opencode-mcp审计节点1/节点2 两条项目记忆，另有工具台反馈文件。

建议：opencode SDK/MCP 可继续用于只读问答、最小 smoke、受控 prompt；暂不建议直接作为会改文件的执行代理接入当前脏分支。若要作为后续执行代理，先满足：每个任务独立 worktree/干净分支；启动前 hard gate 检查 dirty；allowed_prefix/forbidden_prefix 强制执行；设置 OPENCODE_SERVER_PASSWORD；log_tail 脱敏；SDK prompt 禁止未注册 agent 名称；patch part 必须和前后 git diff 基线绑定并标注“既有/新增”。
