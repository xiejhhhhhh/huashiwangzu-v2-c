---
name: "foundation-upgrade-scout-r2-第二阶段升级侦察报告"
type: "reference"
tags: [foundation-upgrade-scout-r2, upgrade-scout, dev-toolkit, mcp, agent, content-ir]
agent: "foundation-upgrade-scout-r2"
created: "2026-07-03T00:45:00+08:00"
---

# 第二阶段升级侦察报告

本轮目标是找框架、工具台、MCP、Agent 与模块体系还有哪些可借鉴的升级空间。原则：不搬开源项目外壳，只蒸馏机制；优先不改代码，只有发现完整小链路才安全修复。

## 参考源

优先使用用户提供的本地参考源目录：

```text
/Users/hekunhua/Documents/Agent/reference_sources
```

本轮重点读取的机制来源：

- `agent_upgrade_2026_06_25_extra/langgraph`：checkpoint、pending writes、thread/checkpoint_id、Postgres saver、store/conformance。
- `agent_upgrade_2026_06_25_extra/OpenHands`：事件存储、事件回放、UI 事件折叠、runtime readiness/sandbox recovery。
- `agent_upgrade_2026_06_25_extra/letta`：provider trace backend、event loop watchdog、工具 schema 生成与 docstring 校验。
- `agent_upgrade_2026_06_25/dify`：workflow event snapshot、pause/resume、SSE snapshot + live buffer。
- `agent_upgrade_2026_06_25/opencode`：durable session inbox、context epoch、permissioned tool registry、context usage metrics。
- `document_json_unification_2026_06_25/unstructured` 与 `pandoc`：自动文件类型路由、element metadata、层级 parent_id、统一 AST/IR 思路。

未新下载开源项目。

## 已顺手修复

### 工具台自检真实 MCP 调用失败

现象：`mcp_self_check` / `dev_toolkit_architecture_audit` 在真实 MCP stdio 调用中返回：

```text
No module named 'dev_toolkit'
```

原因：`dev_toolkit/insight_tools.py` 的组件动态导入只尝试 `dev_toolkit.{component}`。单测通过是因为测试插入了 repo root 到 `sys.path`；但 `server.py` 以脚本方式运行时，顶层 fallback import 已生效，动态 import 仍按包名找会失败。

改动：`_component_tool_names()` 增加 `ModuleNotFoundError` 回退，改为导入同目录模块名。

验证：

```text
python3.14 -m pytest dev_toolkit/test_insight_tools.py
3 passed

真实 MCP stdio 调用 mcp_self_check(include_tools=false)
success: true
```

## 优先升级建议

### P0：工具台 schema 类型升级，减少参数字符串化

当前 `core_tools.py` 里 `probe.body`、`call_capability.params` 仍声明为 string JSON，agent 需要手工序列化，容易出现字段名和 JSON 解析误差。MCP 工具 schema 已支持 object 参数，本项目也有统一响应和 Pydantic 口径，可以把高频工具逐步改成真正的 object 输入。

建议做法：

- `probe.body` 支持 object，兼容旧 string。
- `call_capability.params` 支持 object，兼容旧 string。
- `_verify_tool_args` 增加真实 MCP schema smoke，覆盖 stdio 路径。

收益：降低假红/假绿、减少 agent 手写 JSON 字符串；与当前 `/api/modules/call` 的 `parameters` 契约更一致。

### P0：项目记忆写入防覆盖 + 并发锁

当前 `memory_write()` 由 title slug 决定路径，同 title 会覆盖旧记忆；`_索引.md` 与 embedding cache 是 temp+rename，但没有跨进程锁。多 agent 并发写项目记忆时，存在最后写 wins、索引/cache 丢更新风险。

建议做法：

- slug 冲突时自动追加时间或短 hash，除非显式 `overwrite=true`。
- 对 `开发文档/项目记忆/` 写入加文件锁，保护 memory 文件、索引、embedding cache 三者一致。
- `memory_write` 返回 `overwritten:false/true`，收尾报告可见。

收益：符合“每节点 memory_write”的多 agent 工作流，避免阶段性证据被同名节点覆盖。

### P1：Agent durable event stream 分层

本项目已有 `agent_events`、`timeline`、`agent_checkpoints`、admin replay；但事件体系还没有明确区分：

- durable replayable events：断线后按 cursor 重放，作为事实来源。
- live-only deltas：流式 token、思考片段、工具输入片段，只给在线 UI，不推进 durable cursor。
- projected messages：从 durable event 投影出的会话可见消息。

参考机制：

- OpenHands 事件服务提供存储、过滤、分页和实时流。
- Dify workflow event snapshot 会先重放节点快照，再接 live buffer。
- opencode session spec 明确 durable event tail 与 ephemeral delta 不混淆。

建议做法：

- 给 `agent_events` 增加统一 `seq/cursor` 口径，定义 replay API。
- SSE 首包先发 durable snapshot，再接 live delta。
- `assistant_draft`、tool_call、tool_result、approval_required 等 timeline 事件统一成可投影类型。
- UI 工作组只消费投影，避免流式事件和历史事件两套解释逻辑长期分叉。

收益：断线恢复、审计重放、子 Agent 交付、长任务继续执行都会更稳。

### P1：Agent context epoch / runtime context snapshot

Agent 目前已有 budget guard、context pipeline、prompt provider、tool guidance 和压缩机制，但“本轮到底把哪些系统上下文给了模型”仍散在 prompt、工具列表、记忆注入、模型配置中。

参考机制：

- opencode 的 Context Epoch：把环境事实、项目指令、agent guidance、模型/工具可见性作为一次不可变基线；变化只在安全边界以 chronological system update 进入。
- LangGraph checkpoint 的 thread_id/checkpoint_id 让恢复点明确。

建议做法：

- 每次 provider turn 生成 `context_snapshot_id`，记录模型、provider、system prompt hash、工具目录 hash、记忆注入摘要、文件/知识库引用摘要。
- 快照只存结构化摘要和 hash，不把全部 prompt 大文本重复写爆。
- admin replay 中显示“本轮上下文 epoch 变化”，辅助调参和追责。

收益：回答异常时能知道是模型问题、上下文污染、工具目录漂移，还是压缩/记忆注入造成。

### P1：Provider trace 与成本治理合并成可诊断调用链

当前已有 `agent_usage_daily` 成本统计和模型网关降级链，但单次 provider 调用的 request/response、降级原因、token 细分、latency、错误分类没有统一 trace 表。

参考机制：

- Letta provider trace backend 把 trace 后端抽象成 Postgres/ClickHouse/socket。
- opencode context metrics 把 input/output/reasoning/cache token 与模型 context limit 合并展示。

建议做法：

- 新增轻量 `agent_provider_traces` 或框架级 `framework_model_traces`。
- 字段：conversation_id、turn_id、provider、model、profile_key、request_hash、prompt_tokens、completion_tokens、reasoning_tokens、cache_read/write、latency_ms、fallback_from、fallback_to、error_code、cost。
- admin 面板展示最近失败 trace 与 context usage 百分比。

收益：模型网关、Agent、成本治理不再只能看日聚合，能定位单次异常。

### P1：模块能力契约 conformance gate

当前有 manifest `public_actions`、运行时 `register_capability`、`/api/modules/call`，并已有并行 agent 在审计一致性。建议把审计变成常驻 gate。

建议做法：

- `release_gate` 增加 capability conformance：manifest 声明、runtime 注册、活系统可调用三者对齐。
- 对每个 capability 要求最小 schema：参数名、min_role、side_effect/read_only、是否私有 owner scoped。
- 自动生成 capability catalog 文档，供 Agent tool discovery 使用。

收益：防止“manifest 写了但没注册”“注册了但文档没有”“调用参数 drift”。

### P2：Content IR 吸收 element metadata / hierarchy 机制

本项目 Content IR 已经收口 validate/normalize/write/compile，是正确方向。unstructured 的可借鉴点不是引入它，而是补强 parser 输出元数据：

- element/block id 稳定化。
- parent_id / category_depth 层级关系。
- language、filetype、page、bbox、source metadata。
- 表格/图片资源引用与 block 关联。

建议做法：

- 在 parser capability 返回 blocks 时统一 `source_span`、`page_no`、`bbox`、`parent_id`、`confidence`、`degraded_reason`。
- `validate_ir` 对 parser profile 增加最小 metadata 检查。
- knowledge ingestion 记录 parser degraded reason，避免“解析成功但质量差”被当作成功。

收益：知识库页级融合、证据引用、文档再编辑和 Agent 引用都会更可信。

### P2：工具台组件化继续收尾

`mcp_self_check` 修复后显示 `dev_toolkit/server.py` 仍有约 1678 行，超过 600 行规则；这不是阻塞，但已经是维护债。

建议做法：

- 把 `_brief`、`_plan_task`、`_finish_task` 等大实现继续从 `server.py` 迁入 `core_tools.py` 或独立 service。
- 给每个工具组件加最小 stdio smoke，覆盖“直接 import 单测”和“server.py 脚本 MCP 调用”两种路径。
- `tool_usage_stats` 的 agent 归因目前大量 unknown，可在 MCP server 层支持 `_meta.agent` 或统一读取 `agent` 参数。

收益：降低工具台继续扩展时的导入路径和巨文件维护风险。

## 暂不建议

- 不建议重提 Docker 强隔离。项目已明确 terminal-tools 本地执行边界，OpenHands/Letta 的 sandbox 机制只能借鉴“恢复、状态、权限描述”，不迁移隔离模型。
- 不建议把 LangGraph/Dify/Letta/opencode 任一项目作为运行时依赖替换现有 Agent engine。当前 V2 已经有适合本项目的模块边界和统一能力通路，应该小步吸收 checkpoint、event、trace、schema、gate 机制。
- 不建议把 unstructured/docling 直接塞进框架 parser 主路径。先抽 metadata/profile 规范，再由各 parser 模块按需实现。

## 后续拆任务建议

1. `dev-toolkit-schema-object-r3`：升级 `probe` / `call_capability` object 参数并保持旧 string 兼容。
2. `project-memory-lock-r3`：memory_write 防覆盖 + 文件锁 + 索引/cache 一致性。
3. `agent-event-replay-r3`：定义 durable events / live delta / projection 三层契约。
4. `agent-context-epoch-r3`：落地 context snapshot id 与 admin replay 展示。
5. `model-provider-trace-r3`：把 provider trace 接到网关和 Agent usage。
6. `capability-conformance-gate-r3`：release_gate 增加能力契约一致性。
7. `content-ir-metadata-profile-r3`：补 parser metadata profile 和 degraded reason。

## 本轮验证

```text
python3.14 -m pytest dev_toolkit/test_insight_tools.py
3 passed

真实 MCP stdio:
mcp_self_check(include_tools=false) => success:true
```

## 改动范围

代码改动仅：

```text
dev_toolkit/insight_tools.py
```

文档/记忆新增在：

```text
开发文档/项目记忆/
```

