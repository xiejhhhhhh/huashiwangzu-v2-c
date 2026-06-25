# 深度借鉴机会调研 — 第 1 组：agent 运行时与可恢复执行

- Agent: opencode-agent
- 时间: 2026-06-25（首版）/ 2026-06-25（深度补充）
- 项目: LangGraph、OpenHands

## 核心发现

对照 LangGraph 的 checkpointer 机制和 OpenHands 的工作区生命周期管理，我们当前的 agent runtime 存在两个关键缺口：

### 1. 运行时检查点（P0 缺口）
- **现状**：`tool_loop_runtime.py:88-479` 整个工具循环纯内存，`finally` 块（`:514-538`）才做一次 `sink.persist_assistant()` 持久化。worker 在任意轮次崩溃，整轮对话全丢（仅 user_msg 已入库）。
- **已有**：`AgentMessage`/`AgentEvent` 表存消息历史、`post_turn_hooks` 的 `context_snapshot`（轮次级快照）
- **LangGraph 参考**：`AsyncPostgresSaver`（`langgraph/checkpoint/postgres/aio.py:40`）三表设计（`checkpoints` JSONB + `checkpoint_blobs` BYTEA + `checkpoint_writes`); `PregelLoop._put_checkpoint()` 每 superstep 自动调用; `_first()` 支持 resume 判断
- **建议**：实现轻量 `PostgresCheckpointSaver`（全量 JSONB，不做 DeltaChannel），每轮工具循环后写检查点。三表模型简化版：`agent_checkpoints(id, conversation_id, checkpoint_id, step, channel_values JSONB)` + `agent_checkpoint_writes`

### 2. 对话级工作区隔离（P1 缺口）
- **现状**：`ensure_user_workspace(user_id)`（`workspace_security.py:30`）返回 `data/workspaces/{user_id}/`，同一用户多对话共享。`delete_conversation`（`conversation_service.py:57`）仅 `status="deleted"`，不清理文件。
- **OpenHands 参考**：`AppConversationService`（`app_conversation_service.py:33`）的 `start/delete_app_conversation` 管理完整对话生命周期，sandbox + workspace 与 conversation_id 强绑定
- **建议**：`user_id/conversation_id` 二级分配，create/delete_conversation 时自动初始化/清理工作区

### 排除项
- DeltaChannel（全量 JSONB 够用；`tool_loop_runtime.py` 每轮仅 3-5 变量）
- EventStream（`AgentEvent` 表已够）
- Sandbox Docker 隔离（AGENTS.md 第 21 条已决策）
- Pregel 节点引擎（线性工具循环不匹配；工作流需从 Dify 借）

## 关联文件
- 报告: `收件箱/深度借鉴机会调研-第二轮/借鉴机会清单-第1组-agent运行时与可恢复执行.md`
