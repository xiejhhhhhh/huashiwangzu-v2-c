---
name: "reference-upgrade-scout-r4-下一阶段参考源码升级机会报告"
type: "reference"
tags: [reference-upgrade-scout-r4, upgrade-scout, reference_sources, workflow, private-modules, upload, document-parsing, multi-agent-board, report, 20260703]
agent: "reference-upgrade-scout-r4"
created: "2026-07-02T16:56:41.867158+00:00"
---

# reference-upgrade-scout-r4 下一阶段升级机会报告

## 本轮读取/对照来源

本地参考源目录：`/Users/hekunhua/Documents/Agent/reference_sources`。

重点对照：

- `agent_upgrade_2026_06_25/coze-studio`：Workflow/Plugin/RAG/资源化入口，API-first、领域分层、事件驱动。
- `agent_upgrade_2026_06_25/dify`：workflow event snapshot、节点编排、pause/resume 思路（本轮主要沿 r2 结论补充）。
- `agent_upgrade_2026_06_25/hermes-agent`：插件足迹阶梯、Kanban 多 agent durable board、工具 schema 不硬编码跨工具引用。
- `document_json_unification_2026_06_25/docling`：多格式解析、layout/reading order/table/OCR、统一 DoclingDocument、lossless JSON、MCP/API server。
- 结合当前仓库 CodeGraph、routes、capabilities、db_reverse_audit、probe 和 SQL 只读检查。

## 0. 已顺手修复：workflow ledger 测试数据污染

### 现象

`/api/workflow/definitions` 返回大量 `test-workflow / ledger-test / wf-a / wf-b / wf-c / transition-test / step-lifecycle / api-steps / fail-test`，SQL 统计显示 540 行全是测试名，每类 60 行，时间覆盖 2026-06-25 到 2026-07-02。

### 根因

`backend/tests/test_platform_workflow_ledger.py` 的 `_do_cleanup()` 只删除 `id > 99999`，但测试写入的是普通自增 id，清理条件永远不命中。违反“测试数据创建者负责清理”。

### 修复

已改 `_do_cleanup()`：按固定测试 workflow 名和测试 trace 找 definition/run/step，按 step -> run -> definition 顺序删除。跑该测试后顺带清理了活库旧污染。

### 验证

- `cd backend && .venv/bin/python -m pytest tests/test_platform_workflow_ledger.py -q`：11 passed。
- `cd backend && .venv/bin/ruff check tests/test_platform_workflow_ledger.py`：passed。
- SQL：`framework_workflow_definitions total=0/test_like=0`；测试 trace 残留 0；orphan steps 0。

## 1. 平台 Workflow 从“只读账本”升级为“能力节点编排”

### 参考做法

Coze 把工作流作为可视化节点/资源/API 的完整业务对象；Dify 的 workflow 强调节点执行事件、snapshot 与 live buffer。两者共同点不是大而全 UI，而是：workflow definition -> run -> step ledger -> node executor -> resource refs -> observability 是同一条链。

### 我们现状差距

当前 `backend/app/routers/workflow.py` 自述是 skeleton endpoints，只提供 definitions/runs/steps GET；`platform_workflow.py` 已有 definition/run/step 表和 ResourceRef，但没有 POST 创建、发布、dispatch，也没有 capability node 执行。活库此前全是测试污染，说明这个链路目前主要是测试骨架，不是业务主链。

### 建议落点

- `backend/app/models/platform_workflow.py`
- `backend/app/routers/workflow.py`
- `backend/app/services/workflow_orchestrator.py`
- `backend/app/services/module_registry.py` 或 `/api/modules/call` 统一能力调用入口
- `backend/tests/test_platform_workflow_ledger.py`
- 后续可加 `frontend/src/...` 的轻量运行列表，不急着做画布

### 推荐一期范围

只做后端最小闭环：definition CRUD（admin/editor）、publish 校验、dispatch 一个 `capability_call` 节点、step ledger 记录 input/output/error/duration、失败降级为 failed，不做复杂 UI。

### 风险

中等偏高。它是框架公共能力，必须走统一 capability registry，不能让 workflow 变成第二套跨模块调用机制。

### 是否适合派 worker

适合，但应在当前底座维修 checkpoint 提交后单独派 `workflow-orchestrator-worker-r5`，不要混进 knowledge/memory/frontend 这批改动。

## 2. Private Modules/Plugin 生命周期补成真实可用链路

### 参考做法

Hermes 的“Footprint Ladder”明确：能做成 plugin/MCP/服务门控工具的，不扩核心工具；Coze 把插件、工作流、数据库、知识库、变量都归为资源，并有 plugin template/OAuth schema。

### 我们现状差距

仓库已有 `framework_private_modules`、`/api/private-modules/*` 和 `private_module_service.py`，但活系统 `installed=[]/available_in_workspace=[]`，说明链路没有真实使用。现有 service 可以从 `data/workspaces/{owner}/private_modules` 读取 manifest 并动态 include router，但缺少：manifest schema 严格校验、sandbox 验收、能力注册一致性检查、安装事务/回滚更细的 last-known-good 保护、路由/能力卸载测试。

### 建议落点

- `backend/app/services/private_module_service.py`
- `backend/app/routers/private_modules.py`
- `backend/app/models/private_module.py`
- `modules/_template/manifest.json` 与 `modules/_template/sandbox/`
- `backend/tests/test_private_modules*.py`（若无则新增）
- `dev_toolkit/module_sandbox_matrix.py` 或 release gate 增加 private module package smoke

### 推荐一期范围

把它定义成“用户工作区模块包安装器”，先支持 preview -> sandbox_validate -> install -> activate -> deactivate -> uninstall，全程记录 DB 状态；失败稳定落 `failed/error_message`，不吞异常成假成功。

### 风险

高。动态 router 和能力注册会影响框架路由表，必须做隔离路径、owner 边界、测试包清理和 rollback。

### 是否适合派 worker

适合派一个强 worker，但要禁止大 UI，先做后端生命周期与测试包。

## 3. 大文件/断点上传补齐 FileUploadSession 链路

### 参考做法

Coze 文档强调基础组件配置中的上传组件；OpenHands/Docling 类项目都把文件存储/解析作为后续 RAG、工作流、知识库的入口。关键不是花哨上传 UI，而是上传 session 可恢复、可过期、可观测。

### 我们现状差距

当前只有 `/api/files/upload` 单次 FormData 上传；`framework_file_upload_sessions` 模型存在但 routes(filter='upload') 只有一个 monolithic upload 端点，表为空。`frontend/src/shared/upload/directory-upload.ts` 做目录上传，但没有 chunk/resume。大文件失败时没有 session-level 错误位置。

### 建议落点

- `backend/app/models/file_upload_session.py`
- `backend/app/routers/file_transfer.py`
- `backend/app/services/file_upload_service.py`
- `frontend/src/shared/upload/directory-upload.ts`
- `frontend/src/shared/api/index.ts`
- 后端测试：新增 chunk init/upload/complete/expire/cleanup

### 推荐一期范围

新增 `init_session / upload_chunk / complete_session / abort_session / cleanup_expired`，复用现有 `upload_file_from_path` 入库和 file.uploaded 事件。小文件继续走原端点；大文件/目录上传可选择 session path。

### 风险

中等。要避免产生第二套文件入库逻辑，complete 必须最终调用现有 file_upload_service。

### 是否适合派 worker

适合。它不会干扰当前 knowledge/memory 维修，但和文件主链有关，建议单独 worker + 强测试。

## 4. 文档解析质量 profile：Docling/Unstructured 思路蒸馏到 Content IR + Knowledge

### 参考做法

Docling 强调多格式解析、PDF layout/reading order/table/OCR、统一 DoclingDocument、lossless JSON；Unstructured 的价值在 element metadata、层级、page/bbox/source metadata。我们不应引入整套依赖替换现有模块，而是吸收“解析质量画像”。

### 我们现状差距

本轮 knowledge 已新增 `kb_pipeline_runs/kb_pipeline_stage_runs` 和 raw/fusion diagnostics；历史 failed 里仍有 `Parser returned no content blocks` 质量债。当前 parser capability 的输出还缺统一的 degraded_reason、source_span、page_no、bbox、parent_id、confidence/profile_version 等字段，Content IR 与 Knowledge 之间质量信号还没有完全通用。

### 建议落点

- `backend/app/services/content/ir_*`
- `modules/knowledge/backend/services/raw_collection_service.py`
- `modules/knowledge/backend/services/fusion_service.py`
- `modules/knowledge/backend/models.py`
- parser modules：`text-parser/pdf-parser/docx-parser/pptx-parser/xlsx-parser/structured-parser/*`
- `modules/knowledge/backend/tests/test_pipeline_stage_semantics.py`

### 推荐一期范围

定义 `ParserBlockMetadata` profile，所有 parser 可渐进支持；不支持的字段显式 `null`，解析空内容写 degraded/skipped 原因，不再把“无 blocks”混成硬失败或假成功。

### 风险

中等。涉及多个 parser，但可以先落 schema/profile + knowledge 接收端，再按模块逐步补。

### 是否适合派 worker

适合派 2 个 worker：一个做 contract/schema，一个做 parser 覆盖。不要和当前 knowledge schema 维修同提交混淆。

## 5. 多 agent 工作队列/节点落盘升级为 durable board

### 参考做法

Hermes Kanban 是 durable board：任务、指派、claim、heartbeat、comment、complete/block、failure_limit、dispatcher，worker 使用专用 toolset，避免每个 worker 都背全量核心 schema。

### 我们现状差距

当前项目已有 mailbox、项目记忆、MCP feedback、外部 subagent 通知，但“主会话指挥家 -> 多 worker -> 节点落盘 -> 回收报告 -> 失败重派”仍偏人工协议。用户已经明确要求节点落盘和额度中断不丢记忆，项目工具台可以把这个常态化。

### 建议落点

- `dev_toolkit/*` 新增 `agent_board_tools.py`
- `开发文档/项目记忆/` 继续作为报告输出，不作为唯一状态机
- 可选后端表：若要跨进程强一致，可用 `framework_workflow_*` 或新增工具台本地 sqlite/json lock，先不要污染业务 DB
- release gate 加 board smoke：创建任务、claim、heartbeat、complete、block

### 推荐一期范围

先在 dev_toolkit 内做轻量 board：任务 markdown + lock/heartbeat JSON 原子写，提供 MCP 工具 `board_create/claim/update/complete/block/list`。后续再和 workflow 框架合流。

### 风险

低到中。风险主要是不要发明第二套业务 workflow；它应当定位为开发工具台的 agent 协作板。

### 是否适合派 worker

适合派 devtool worker，且最符合用户当前“5 个常驻子代理、节点落盘”的工作方式。
