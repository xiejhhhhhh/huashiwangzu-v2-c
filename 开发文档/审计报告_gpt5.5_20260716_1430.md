# 审计报告 GPT-5.5

生成时间：2026-07-16 14:30 左右（本地会话）
执行者：Codex / GPT-5.5
范围：当前仓库全局只读审计；除本报告外未修改产品代码、配置、数据库或运行态。

## 结论摘要

本轮审计没有发现后端整体不可用：`sanity_check` 显示前端 5173、后端 `/api/health`、模块导入均为正常，后端健康返回 `database=ok`、`worker_mode=external`、`pending=0`、`running=0`。

但存在 5 类需要收口的问题：

1. `knowledge:align_entity_batch` 是运行时已注册的 admin 写库能力，但没有出现在 manifest `public_actions`，且没有声明 execution contract。该问题已被 `capability_contract_diff` 和 `docs_audit` 判为 drift/blocker。
2. 近期日志出现 `/api/modules/call` 60 秒超时，并伴随 asyncpg/SQLAlchemy rollback 连接已关闭异常；触发点与 knowledge 实体打齐长耗时调用高度相关。
3. 后台任务没有当前积压，但存在 422 条历史 failed 债务，其中 340 条来自 `kb_enterprise_import_file`，57 条来自 `kb_pipeline_stage`。
4. `diagnose` 工具的数据库连通性检查使用了错误库名 `huashiwangzu_v2`，在实际数据库名为 `华世王镞_v2` 的项目里会产生误报。
5. 文档同步存在系统性债务：`modules/model-router/README.md` 缺失被判 BLOCKER，多个模块 README 缺少 capability source / acceptance section。

## 证据清单

本轮主要使用 MCP 与少量代码定位：

- `plan_task(task_type=investigation)`：确认纯审计流程。
- `brief`：确认当前分支、工作区、项目概况和既有 dirty 文件。
- `sanity_check`：后端健康、模块导入、前端端口均通过。
- `bug_logs(lines=1200,severity=all)`：抓到 `/api/modules/call` 超时与 asyncpg rollback 异常。
- `capability_contract_diff(include_parameters=true)`：发现 `knowledge.align_entity_batch` runtime-only。
- `docs_audit`：返回 BLOCKER，包含 capability drift 和 `modules/model-router/README.md` 缺失。
- `context_load(module=knowledge)` / `code_node` / `code_explore`：定位 knowledge router 和能力注册实现。
- `knowledge_pipeline_snapshot`：确认 pipeline 无 pending/running，剩余 57 个阶段失败。
- `db_schema` / `sql`：确认实际任务表是 `framework_system_task_queues`，并统计状态。
- `agent_board_snapshot` / `opencode_sdk_job_list`：检查是否存在活跃并行审计 owner；当前无 open/claimed，历史有 stalled/blocked 审计任务。

## 发现 1：knowledge 写库能力未进入 manifest，且缺少风险契约

级别：P1 / Release blocker

证据：

- `capability_contract_diff` 返回：`knowledge` 模块存在 runtime-only action `align_entity_batch`，位置 `modules/knowledge/backend/router.py:1385`。
- `docs_audit` 返回 `BLOCKER`，其中包含 `capability_drift`。
- 代码中 `_cap_align_entity_batch` 位于 `modules/knowledge/backend/router.py:1313`，注册位于 `modules/knowledge/backend/router.py:1385`。
- `context_load(module=knowledge)` 的 manifest capability 列表没有 `align_entity_batch`。

代码事实：

- `_cap_align_entity_batch` 会读取 `kb_entity_dictionary`，并并发执行 `canonicalize_name`、`_resolve_canonical_entity`、`_merge_variant_into`。
- 它会更新 `kb_entity_dictionary.align_status='done'`，并在合并时写入实体归并相关数据。
- 注册时 `min_role="admin"`，但没有传 `execution_contract`；按 `module_registry._normalize_execution_contract` 默认值，未声明能力会被标为 `side_effect_level="none"`、`approval_policy="none"`、`timeout_seconds=30`、`parallel_safe=false`。

影响：

- 发现目录、manifest、README 与运行时不一致，发布门禁/文档审计会持续失败。
- Agent 或能力目录可能无法稳定解释该能力的真实风险，尤其是它实际会写库、耗时、并发开 DB session、可能调用 LLM 裁定。
- 默认 timeout/risk metadata 与实际行为不匹配，容易被调度为“普通 fast capability”。

建议：

- 二选一收口：如果这是内部回填脚本专用能力，应改为内部/私有/非 discoverable 的任务通道，不放在公共 capability surface；如果确实要公开给 admin，则补入 `modules/knowledge/manifest.json public_actions`。
- 同步补 `execution_contract`：建议至少标记 `side_effect_level="admin"` 或 `admin_config`、`resource_class="llm_db_write"`、`timeout_seconds>=1800`、`idempotency="supported"` 或明确 `none`、`approval_policy="requires_confirmation"`、`parallel_safe` 按真实分片安全性声明。
- 给该能力加最小测试：manifest/runtime drift 测试和参数边界测试，尤其是 `batch_conc`、`shard/shards`、异常后 `align_status` 是否会无限 pending。

## 发现 2：实体打齐类长耗时调用导致 `/api/modules/call` 超时和 DB rollback 异常

级别：P1 / 运行稳定性

证据：

- `bug_logs` 在 `backend/logs/backend.log` 近 1200 行内抓到：
  - `13:41:49 [v2.timeout] WARNING Request timeout after 60s: POST /api/modules/call`
  - `INFO: 127.0.0.1 ... "POST /api/modules/call" 504 Gateway Timeout`
  - `13:42:17 [v2.handlers] ERROR Unhandled exception on POST /api/modules/call: ... cannot call Transaction.rollback(): the underlying connection is closed`
  - 前后文有 `knowledge.router` 警告：`align实体2816(...)异常`。
- 日志中同一次调用有 `gateway.usage`：`model=deepseek-v4-flash ... duration=87319ms`，超过 60 秒请求超时阈值。
- `_cap_align_entity_batch` 使用 `asyncio.gather` 对 batch 内实体并发处理，每个实体单独打开 `AsyncSessionLocal()` 并 commit。

影响：

- HTTP 请求 60 秒超时后，后端内部任务仍可能继续执行或进入异常清理，导致连接已关闭时 rollback，再把原始异常噪声放大成 ASGI unhandled exception。
- 该类能力本质是后台批处理，不适合直接通过同步 `/api/modules/call` 长时间运行。
- 单次 batch 默认 100、`batch_conc` 默认 8，且可由参数调大，存在 DB 连接压力和模型调用时间不可控风险。

建议：

- 将 `align_entity_batch` 从同步 capability 改为后台任务：调用只负责投递 task，执行器按 lease/heartbeat/重试/限流处理。
- 如果短期保留同步能力，需要在 handler 内限制 `batch` 和 `batch_conc` 上限，并声明 execution contract 的长 timeout 与写库风险。
- 对 `/api/modules/call` 的 timeout 后清理路径补专项测试，确保请求取消不会触发 rollback-on-closed-connection 噪声。

## 发现 3：任务队列当前无积压，但历史 failed 债务仍明显

级别：P2 / 运营债务

证据：

- `/api/health` 返回：`task_queue.pending=0`、`running=0`、`failed=422`、`historical_failed_debt=422`、`debt_status="debt"`。
- `knowledge_pipeline_snapshot` 返回知识库 pipeline：总计 `pending=0`、`ready=0`、`running=0`、`failed=57`、`completed=265378`。
- SQL 统计 `framework_system_task_queues`：
  - `completed=291904`
  - `failed=422`
  - `cancelled=3`
- failed 任务类型分布：
  - `kb_enterprise_import_file=340`
  - `kb_pipeline_stage=57`
  - `profile_evolve=7`
  - `memory_distill=6`
  - `agent_context_compact=6`
  - `kb_pipeline=4`
  - `kb_chunk_embedding_backfill=1`
  - `agent_execute_slow_tool=1`
- `knowledge_pipeline_snapshot.recent_failures` 中既有真实坏文件/不支持内容，也有 `Dispatcher lease expired; task released for retry`、`document_already_parsing`、`file_not_found`。

影响：

- 当前不是“卡住”，但健康页仍长期带 failed debt，会降低 release gate 和运维信号可信度。
- 一部分是不可恢复坏文件，一部分是过期 lease/重复解析锁，应该分类归档，否则新失败不容易被看见。

建议：

- 对 `kb_enterprise_import_file` 的 340 条失败单独分类：区分源文件不存在、损坏、不支持格式、可重试模型/解析异常。
- 对 `kb_pipeline_stage` 57 条失败继续用 `knowledge:classify_pipeline_debt` dry-run 分类，然后 guarded apply：不可恢复归档，可恢复重试。
- 健康接口可继续保留 historical debt，但建议同时展示 `new_failed_since_baseline` 或最近 24h 新失败，避免历史债遮蔽新事故。

## 发现 4：诊断工具数据库检查存在库名误报

级别：P2 / 工具可信度

证据：

- `diagnose(module=knowledge, error_query=...)` 返回 `success=false`，失败项为 database：`psql: error: connection to server on socket "/tmp/.s.PGSQL.5432" failed: FATAL: database "huashiwangzu_v2" does not exist`。
- 同一轮 `sanity_check` 的后端健康显示 `database="ok"`。
- `db_schema` 能正常列出表，`sql` 能正常查询 `framework_system_task_queues`。
- 项目 README 明确数据库名是 `华世王镞_v2`，不是 `huashiwangzu_v2`。

影响：

- `diagnose` 在数据库实际可用时返回失败，会误导审计/运维优先级。
- 后续 agent 可能把工具误报当成真实 DB 故障。

建议：

- `diagnose` 的 DB 连通性不要硬编码 romanized db name，应复用后端 `.env` 或项目数据库配置。
- 诊断输出中区分“工具自身连接失败”和“后端应用数据库失败”；当前 evidence 更支持前者。

## 发现 5：文档同步 BLOCKER 和 README 债务仍未收口

级别：P2 / 发布治理

证据：

- `docs_audit` 返回 `level=BLOCKER`，汇总 `blockers=2`、`debts=62`、`issues=64`。
- BLOCKER 包括：
  - `capability_drift`：对应发现 1。
  - `missing_module_readme`：`modules/model-router/README.md`。
- 多个模块 README 缺 `missing_capability_source` 或 `missing_acceptance_section`。

影响：

- 文档审计门禁不能作为绿色发布信号。
- 新 agent 接手模块时，容易依赖过期 README 或缺少验收命令，增加重复探索成本。

建议：

- 优先补 `modules/model-router/README.md`，至少包含：模块定位、对外能力、接口、数据表/无表说明、验收命令。
- 运行 `docs_sync(dry_run=true)` 预览，再分批刷新模块 README 的 DOCS-SYNC 区块。
- 先处理 BLOCKER，再分批处理 62 条 DEBT，不建议一次性机械改全仓 README，避免文档噪声过大。

## 发现 6：并行审计状态未登记为活跃，但历史有 stalled/blocked 审计任务

级别：P3 / 协作可见性

证据：

- `agent_board_snapshot(status=open)` 返回 open/claimed 均为 0，当前没有活跃 owner。
- 事件历史中存在旧审计类任务：`agent-capability-audit-20260704` 后续被标 blocked；OpenCode SDK job list 中也有 7 月 3 日的只读审计 job 处于 stalled。
- 当前工作区 dirty 仅有一个 untracked：`scripts/create_market_sales_word.py`，不是本轮审计产生。

影响：

- 如果用户实际启动了未登记到 agent board 的并行 agent，本轮无法从 board 识别；只能通过工作区边界避免冲突。
- 历史 stalled 审计任务如果不清理，容易让后续 agent 误判“仍有人在跑”。

建议：

- 并行审计任务统一写 agent board claim/heartbeat/complete，纯审计也建议登记，避免重复审同一范围。
- 对历史 stalled/blocked job 做一次归档或标注，区分“历史遗留”与“当前活跃”。

## 未判为问题但需说明

- `/api/modules/call` 入口本身是 viewer 权限，但不是直接越权：`backend/app/routers/modules.py` 入口调用 `call_capability_for_user`，最终 `module_registry.call_capability` 会进入 `_authorize_user_capability`，再由 `permission_service.assert_capability_authorized` 做 SQL 权限裁定。风险不在入口权限，而在 runtime/manifest/contract 对能力真实风险表达不一致。
- `knowledge_pipeline_snapshot` 显示 `fusion` 阶段历史指标中 `fusion_model_wall_ms` 很大，但当前 pipeline 没有 pending/running，本轮不把它判为现行卡死。
- `tail_log(module=backend)` 返回空文本，但 `bug_logs` 能从 `backend/logs/backend.log` 抓取异常；本轮以 `bug_logs` 为日志证据。

## 建议修复优先级

1. 先收口 `knowledge:align_entity_batch`：决定它是内部后台任务还是公开 admin capability；同步 manifest 和 execution contract。
2. 把实体打齐从同步 `/api/modules/call` 拆到后台队列或至少加参数上限和 timeout/risk 元数据。
3. 修 `diagnose` 数据库名误报，避免后续排障被工具自身错误干扰。
4. 对 422 条 failed 任务债务做分类治理，优先 `kb_enterprise_import_file` 与 `kb_pipeline_stage`。
5. 补 `modules/model-router/README.md`，再分批处理 docs_audit 的 README DEBT。

## 本轮落盘

仅新增本报告文件；产品代码、数据库、运行服务未改动。

## 二次审计补充（2026-07-16 15:00）

用户反馈“感觉还有不足”后，追加做了一轮只读深挖，重点补查权限身份表、DB 反向链路、前端/runtime 契约扫描。结论如下。

### 补充 1：`align_entity_batch` 没有 viewer 越权，问题收敛为发现层与风险契约漂移

第一轮报告已经说明 `/api/modules/call` 入口本身不是直接越权；二次审计进一步确认：

- `framework_capability_identities` 中已有 `knowledge / align_entity_batch`，`id=91219`，`enabled=true`。
- `framework_capability_permission_requirements` 已绑定 `capability.legacy.admin`。
- 用 viewer 账号直接调用 `knowledge:align_entity_batch` 返回 `403 Capability is not available for the current user`。

因此，这个问题不是 SQL 权限裸露。当前应把风险定性为：runtime 能力已存在并可由 admin 调用，但 manifest/README/能力发现元数据缺失，且 execution contract 默认为低风险 fast capability。修复优先级仍是 P1，但修复目标应聚焦在 manifest、execution contract、后台化和超时治理。

### 补充 2：DB 反向审计未发现明显孤儿表，但发现一个知识库历史/治理表不对称

`db_reverse_audit` 对 `framework_`、`agent_`、`kb_`、`douyin_`、`excel_`、`im_` 前缀做了只读反向审计。

高价值发现：

- `kb_entity_noise_review` 有 `12449` 行数据，但代码引用数为 0，被标记为 `data_without_code_reference`。
- 这不像空表债务，而更像历史治理脚本或临时审计表已经留下数据、当前代码路径不再读写。
- 需要人工确认该表是否仍有产品价值；如果是历史治理残留，应补文档说明和归档策略；如果仍应参与实体清洗，需要恢复显式 service/capability/README 链路。

不建议升级为“可删除”：本轮只读审计没有证明这些数据无用。

### 补充 3：多组空表更像未启用业务链路，不宜直接判 bug

反向审计发现多组 `code_without_data` 空表，但没有看到明显 orphan table：

- `douyin-delivery`：`douyin_accounts`、`douyin_ad_copies`、`douyin_campaigns`、`douyin_delivery_tasks`、`douyin_materials`、`douyin_products`、`douyin_scripts` 均为 0 行，只有 `douyin_prompts=7`。
- `agent`：`agent_configs`、`agent_enterprise_profiles`、`agent_market_profiles`、`agent_role_profiles`、`agent_tool_guide_candidates`、`agent_usage_daily` 等为空，但多为可选配置/画像/候选表。
- `framework`：`framework_circuit_breaker_states`、`framework_file_upload_sessions`、`framework_private_modules`、`framework_system_feedbacks`、`framework_system_trace_spans`、`framework_workflow_*` 等为空。
- `excel-engine`：`excel_redo_stack=0`，但 `excel_history=2`、`excel_workbooks=48`、`excel_cells=832`。

这些空表当前更适合进入“业务链路待探测清单”，不应直接作为 P1/P2 bug。建议后续按模块做 happy path 探针，确认 UI/API 是否承诺了这些能力。

### 补充 4：前端/runtime 静态扫描未发现明显假绿模式，但仍有少量手写 helper 值得统一

静态扫描范围：`frontend/src` 与 `modules` 下 TS/Vue/JS 文件。

结果：

- 未命中 `as any`、`@ts-ignore`、`@ts-expect-error`、`success && response.status==200`、`response.status===200` 这类明显类型压制/假绿模式。
- 裸 `fetch` 主要集中在模块 runtime 模板和少量模块前端 helper。
- 抽查 `modules/agent/frontend/api.ts`、`modules/ppt-viewer/frontend/api.ts`、`modules/knowledge/frontend/composables/useKnowledgeWorkspace.ts`：均有鉴权头或 401 处理，未发现直接无鉴权读取。

保留改进建议：

- `modules/agent/frontend/api.ts` 仍有 `initHeaders as Record<string, string>` 这种类型断言，不是 `as any`，但可以后续用 `HeadersInit` 规范化函数减少断言。
- viewer/download 类 blob helper 分散在多个模块，虽然现在带鉴权，但可长期收口到 runtime 公共 blob/download API，降低重复实现漂移。

### 补充 5：`docs_audit(module=knowledge)` 将 knowledge 范围缩小后仍是 BLOCKER

全局 `docs_audit` 的 BLOCKER 很多；缩小到 knowledge 后仍返回：

- `BLOCKER capability_drift`：仍是 `align_entity_batch`。
- `DEBT missing_capability_source`：`modules/knowledge/README.md`。

这说明 knowledge 本身即可独立阻塞文档/能力契约门禁，不只是全局文档噪声。

### 二次审计后的优先级修订

1. 保持第一优先级：治理 `knowledge:align_entity_batch` 的 manifest、README 和 execution contract，并考虑后台化。
2. 新增第二优先级：审查 `kb_entity_noise_review` 的来源和使用状态，决定恢复代码链路、归档说明还是迁移治理产物。
3. 空表清单暂不按 bug 修；先对 `douyin-delivery`、`agent profile/config`、`framework trace/private modules` 做有目标的 happy path 探针。
4. 前端/runtime 当前未见明显假绿/类型压制 P1，可作为后续一致性重构，不进入本轮高优先级修复。

## 第三次深度审计补充（2026-07-16 16:00）

第三轮继续保持纯审计边界，新增检查了鉴权和分享权限、跨 owner 数据隔离、图谱/证据/画像不变量、任务 lease 与取消语义、事件重试、多进程资源上限，以及最近 5 个知识库核心提交。没有发现证据充分的 P0；确认了多项 P1/P2，其中部分已由数据库和真实 HTTP 响应复现。

### 第三轮量化总览

| 检查项 | 结果 | 性质 |
|---|---:|---|
| `kb_graph_edges` 总量 | 170,836 | 基数 |
| 按 graph node id 无法解析端点的边 | 890 | 现存完整性异常 |
| 其中 missing source / target | 624 / 266 | 现存完整性异常 |
| `(owner_id, entity_id)` 重复 graph node | 103 组 | 现存重复数据 |
| 跨 owner `kb_file_relations` | 185,920 | 现存隔离异常 |
| relation owner 与 source owner 不一致 | 92,960 | 现存隔离异常 |
| relation owner 与 target owner 不一致 | 92,960 | 现存隔离异常 |
| 指向 deleted document 的 relations | 1,961,618 | 现存陈旧边 |
| 非零 `chunk_id` 指向不存在 chunk 的 evidence | 18,296 | 现存证据断链 |
| `chunk_id=0` evidence | 50 | 现存证据断链 |
| graph done 但无 `kb_chunk_entities` | 1,125 | 阶段假绿候选 |
| 其中 fused text 超过 100 字符 | 993 | 高置信假绿候选 |
| profile done 但无 active profile vector | 10,856 | 阶段假绿/欠产出 |
| 上述同时 relation done | 10,637 | 级联假绿 |
| graph running 超过 24 小时 | 3 | 陈旧运行态 |

过去 7 天仍新增：117 条断 chunk evidence、47 条图谱孤儿边、674 个 graph done 但无实体关联文档。跨 owner file relation 过去 7 天没有新增，主要是 2026-07-06 至 2026-07-07 的历史遗留；但读取端缺少防御过滤，历史数据当前仍可进入 API 响应。

### 发现 7：read-only 文件分享可修改 owner 的 ContentPackage

级别：P1 / 授权与内容完整性

证据链：

- `backend/app/services/file_share_service.py:41` 的 `check_file_write_access()` 才要求 owner 或 `edit` share。
- `backend/app/services/file_service.py:445` 的 `check_file_access()` 接受任意有效 share，包括 `read`。
- `backend/app/services/content/package_service.py:315` 的 `get_package()` 对非 owner 只调用读取授权；`update_blocks`、`replace_text`、`append_blocks`、`restore_version` 在 `:426`、`:484`、`:535`、`:609` 复用该结果后直接创建版本和切换 `current_version_id`。
- HTTP 写入口位于 `backend/app/routers/content.py:156`；capability 写入口从同文件 `:465` 开始，二者均没有把 share permission 提升为 write check。
- `store_analysis_resource` viewer capability 也只检查 read access，随后可向 owner package 添加 `ResourceRef`。
- 新版本的 `created_by` 被写为 package owner，而不是实际分享接收者，进一步造成审计归因错误。

影响：持有 `read` share 的 editor 可以篡改、追加、替换或回滚 owner 的规范内容；读取权限被错误提升为写权限。

建议：所有 ContentPackage 写操作统一要求 `check_file_write_access()`；pipeline、export、resource 写入分别明确 read/edit 语义；补 owner A 向 editor B 分享 `read`/`edit` 的 HTTP 与 capability 权限矩阵测试。

### 发现 8：跨 owner 文件关系已可通过真实 API 返回

级别：P1 / 数据隔离与元数据泄露

数据库事实：

- `kb_file_relations` 中有 185,920 条 source/target owner 不一致的关系。
- 其中 92,960 条 relation owner 与 source owner 不一致，92,960 条与 target owner 不一致。
- 历史样本包含 owner 4 的 source document `2213` 指向 owner 1 的 target document `2337`。

代码事实：

- `modules/knowledge/backend/services/relation_service.py:402` 的 `get_file_relations()` 只按 `source_document_id` 查询，并在 `:418` 仅按 target id 补文件名，没有校验 relation owner、target owner 或 target deleted。
- 路由只先验证 source document 属于当前用户，不能保证返回的 target 同 owner。
- `get_relation_graph()` 在 `:439` 只按 relation row 的 `owner_id` 过滤，补节点时同样不复核两端文档 owner/deleted。

活系统复现：

- 以 owner 4 的认证上下文请求 `GET /api/knowledge/documents/2213/relations` 返回 HTTP 200。
- 响应中包含 relation `1999819` 和 `2012811`：`source_document_id=2213`、`target_document_id=2337`、`target_filename="凝萃柔润霜 (2)"`。
- SQL 回查确认 source owner=4、target owner=1。接口因此实际披露了其他 owner 的 document id、文件名、关系类型、相似分数和部分证据字段。

建议：读取时把 source/target document 与当前 owner 做双端 join，并过滤 deleted；不要信任 relation row 自带 owner。先修读取防御，再离线隔离/重建 185,920 条历史跨 owner 边和 1,961,618 条 deleted-document 边。

### 发现 9：图谱重建会删除 owner 级共享节点，失败时覆盖旧的可用结果

级别：P1 / 数据完整性与并发

证据：

- `modules/knowledge/backend/services/entity_service.py:537-574` 按当前 document 的旧 evidence 取 entity ids，随后删除这些 entity 对应的所有 owner 级 graph edges 和 graph nodes，并立即 commit。
- `KbGraphNode` 没有 `document_id`；节点语义是 owner/entity 级共享。单文档重建删除共享节点，会影响同 owner 的其他文档。
- 清理发生在新结果写入前；后续实体、证据、节点和边又分多次 commit，无法原子恢复旧图。
- 并行文档任务可能一边引用节点，一边被另一任务删除节点，符合现存孤儿边的形成条件。
- 数据库没有 edge-to-node FK，也没有 graph node `(owner_id, entity_id)` 唯一约束；当前已有 890 条孤儿边和 103 组重复节点。

具体假绿样本：

- document `18334` 有 fusion/profile 内容，但 graph stage 记录 `done`、`entities_found=0`、`relationships_found=0`、`errors=[]`。
- 日志中实体模型调用 `ok=False`、`output_chars=0`，首选 `gpt-5.5-knowledge` 因 401 Unauthorized 失败；之后仍记录 `Cleared old entity/graph data` 和 graph done。
- 当前代码只在 `processed_pages > 0 and not seen_entities and stats["errors"]` 时标 degraded；模型失败若没有进入 `errors`，空结果仍可能完成。

建议：共享 graph node 不应由单文档重建删除；改为文档-实体/证据引用计数或只清当前文档的关联数据。新图应 staging 后原子切换；模型失败和非预期空结果必须 fail/degraded，禁止先清旧结果。

### 发现 10：证据链仍持续写入无效 chunk 引用

级别：P1 / 可追溯性

证据：

- 现有 18,296 条非零 `kb_evidence.chunk_id` 指向不存在的 `kb_chunks.id`，另有 50 条 `chunk_id=0`。
- 无效记录集中在 `source_round=fusion`、`claim_type=entity`、`missing_chunk`；过去 7 天新增 117 条。
- `entity_service.py:712-723` 在 page 没有 chunk 时仍以 `first_chunk_id = 0` 写 evidence。
- 旧抽取路径 `entity_service.py:361-384` 同样保留 `chunk_ids[0] if chunk_ids else 0`。
- 注释已经承认旧版本 `chunk_id=0` 会导致不可追溯，但写入逻辑仍允许该状态。

建议：没有有效 chunk 时不要创建伪 evidence；将其转为明确 degraded/待补索引状态，或让 chunk_id nullable 并用 page fusion/raw data 作为受约束的替代来源。补 DB FK/检查约束前先清查 18,346 条断链记录的可恢复性。

### 发现 11：lease fencing 和人工取消不能阻止已启动 handler 的业务副作用

级别：P1 / 任务一致性

证据：

- `backend/app/services/task_dispatcher.py:863-941` 只在 handler 完成后的 task 最终结算使用 `task_id + running + lease_token` fencing。
- knowledge raw/fusion/entity 服务会在独立 session 中逐页、逐阶段或分批 commit；外层 pipeline rollback 无法撤销这些提交。
- `backend/app/routers/tasks.py:247-262` 的取消接口只把 task 标为 failed；不会立即清 lease，也不直接终止 executor。
- executor 要等 dispatcher 后续 heartbeat 发现续租失败，才在 `task_dispatcher.py:1041-1106` 执行 SIGTERM/SIGKILL。

影响：旧 executor 即使失去 lease 或任务已显示取消，仍可能继续模型调用和业务表提交；新 executor 重领后可与旧 executor交错删除/写入。task row 的最终 fencing 不能证明业务副作用只执行一次。

建议：handler 在每个业务 commit 前验证 execution token/lease；取消需有明确 cooperative cancellation token，并由 executor 直接响应。对 raw/fusion/entity 注入 lease loss 和 cancel barrier，验证旧 executor 后续 commit 被拒绝。

### 发现 12：事件超时重领可与原 handler 并发执行同一事件

级别：P1 / 重复副作用

证据：

- `backend/app/services/event_bus.py:171-223` 将事件标为 processing 后，在事务外执行 handler。
- `:361-397` 对 processing 超过 1200 秒的事件直接重置 pending，再由 retry worker 领取。
- 没有确认原 handler 已停止，也没有 handler execution token fencing。
- 现有测试覆盖多个 retry worker 对 pending 的互斥领取，但未覆盖原 processing handler 仍在运行。

影响：慢 I/O 或卡住的原 handler 与 retry handler 可同时执行，产生重复文件、通知、索引或其他业务副作用。

建议：重领前使用执行租约和 fencing token；业务 handler 使用幂等键。增加“原 handler 持续运行时过期重领”的并发测试。

### 发现 13：多进程 executor、页级 gather、每进程资源池构成乘法压力

级别：P1 / 容量与级联故障

证据：

- 每个 task executor 是独立进程，并初始化独立 SQLAlchemy engine；默认每进程 `pool_size=20`、`max_overflow=10`。
- task worker 配置允许 32 executors；仅理论 DB pool 上限即可达到 960，尚未计 API、dispatcher 等进程。
- fusion/raw/entity 内部还有页级 gather 和独立 session。
- knowledge 模型 active count/Condition 是进程内、event-loop 内状态，不是跨 executor 全局限流。
- 配置中存在 `entity_extract=32`、`model_call_global=200` 等高并发值，task worker 注释已记录历史 PostgreSQL `too many clients`。

影响：连接池、模型并发和页级并发按 executor 相乘，可能导致 pool timeout、too many clients、heartbeat 延迟、lease 过期，进一步触发发现 11 的重复执行。

建议：建立跨进程 DB/model 全局预算；executor 不应各自拥有 30 个潜在连接。用 `pg_stat_activity`、lease renewal latency、provider in-flight 做阶梯压测并确定硬上限。

### 发现 14：最近语义打齐提交存在并发认领、缓存与事务回退缺口

级别：P1 / 最近提交回归风险

针对提交 `3557a144e` 的只读 diff 与当前代码审阅发现：

- `align_entity_batch` 只读取 `align_status=pending`，没有 `FOR UPDATE SKIP LOCKED`、processing 状态或请求级认领；多个 HTTP 请求可处理同一实体。
- `batch`、`batch_conc` 直接转 int 且无上限，每项独立 session；极大参数会放大连接、LLM 和并发写竞争。
- canonical entity/alias 路径是 query-then-insert/merge，未看到覆盖该竞争路径的统一锁或足够唯一约束。
- 字位权威预计算表查询失败后，代码尝试在同一 session 回退；若表不存在导致 PostgreSQL transaction aborted，没有 rollback/savepoint 时后续回退查询也会失败。
- 权威快照未命中时，实体仍可能最终标 `align_status=done`，导致新实体或语料变化后的纠错被永久跳过。

建议：将回填改为有 claim token 的后台任务；参数硬限流；预计算表纳入正式 schema/migration；缓存 miss 与模型异常不得标 done；补同一 canonical 并发合并测试。

### 发现 15：最近治理/重融临时脚本存在可导致数据丢失或层间不一致的行为

级别：P1 / 运维脚本风险

以下结论来自最近 5 个提交的 diff 审阅。相关临时文档正在被其他并行 agent 移动/归档，因此路径按提交时事实记录，不推断当前文件可直接执行：

- `8add5522c` 的回滚脚本把窗口扩大到 24 小时，并只按 anchor `entity_id` 转移引用；锚点自有证据和多个变体证据可能全部被错误转给当前变体。
- `b1628ef11` 的图片重融脚本只更新 page fusion，没有重新 `index_fusions_to_chunks` 或重新抽实体，造成页面正文、搜索 chunk、实体/图谱多层不一致。
- 同提交的跨文档因果脚本在使用 `--limit` 时先删除 owner 全量主体/关系，再只重建 limit 范围；`--limit 10` 可清掉其余数据，且 `--rebuild` 参数未实际控制该行为。
- 图片扩展名条件使用 `.jpg/.png`，而数据库 extension 实际是不带点的 `jpg/png`；图片 OCR/VLM 内容可能被误当成干净文本参与权威统计和实体裁定。
- 技术噪音清理只把实体标 archived，因果层构建未过滤 archived，噪音仍可成为主体/关系节点。
- `9927e59a2` 的实体分类允许输出集合不包含输入中存在的 `术语/通用/其他`，与“不确定时保持原类目”的规则矛盾。
- 实体裁定异常或无 JSON 时返回“留, 0.0”，循环对“留”立即结束，router 后续仍可能标 done；低置信/模型异常不会进入人工复核。

建议：所有治理脚本先提供 dry-run、影响行数、run id 和可逆 journal；禁止“全量 delete + limit 重建”；图片重融必须触发下游 chunk/entity/graph 版本一致性更新；为回滚、重融、因果 limit、分类 fallback 建立自动化往返测试。

### 发现 16：画像和关系阶段存在大规模级联假绿

级别：P2 / 状态可信度

证据：

- `kb_document_profile_vectors` 的有效状态是 `active`，不是 `ready`；按真实口径统计，有 10,856 个 profile done 文档缺 active vector。
- 其中 10,637 个 relation status 仍是 done，且没有实际 `kb_file_relations`。
- 日志对缺 embedding 使用 `No profile/embedding ... skipping relations`，但上层状态可继续完成。
- 当前另有 3 个 graph status 超过 24 小时仍 running。

影响：done 同时表示“成功产出”和“因前置缺失而跳过”，运行看板与下游无法区分完整、degraded、skipped、空产出。

建议：统一 stage result schema，至少区分 `done_with_output`、`skipped_missing_dependency`、`degraded_model_failure`、`failed`；状态写入时校验最小产出不变量。

### 发现 17：过期分享仍可通过 desktop 搜索枚举文件元数据

级别：P2 / 元数据泄露

- `modules/desktop-tools/backend/router.py:104` 的 shared 子查询只检查 `shared_with_user_id`，没有检查 expiry。
- 该 viewer capability 返回 file id、名称、扩展名和大小。
- 权威分享检查明确要求 expiry 为空或大于当前时间；实际内容读取会拒绝过期 share，所以本项定为 P2。

建议：搜索复用统一有效分享 predicate；补刚过期、未来过期和 null expiry 三类测试。

### 发现 18：`knowledge:export` 对裸 trusted system caller 跳过 owner 隔离

级别：P2 / 受信边界 fail-open

- `call_capability_as_system(..., on_behalf_of_user_id=None)` 可形成 `system:*` caller；非 user caller 不进入用户 capability 授权。
- knowledge export 只为 `user:*` 解析 owner；system caller 得到 `owner_id=None`，跳过 document owner 校验。
- export service 在 owner_id=None 时仅按 document id 查询完整文档、chunks 和 page fusions。
- 当前未找到普通 HTTP/Agent 用户直接触达该裸 system 分支，因此这是受信系统路径风险，不与发现 8 的已复现普通读取混为一谈。

建议：system caller 导出必须显式提供 on-behalf user 或受约束 tenant context；`None` 应 fail closed。

### 发现 19：其他事务、超时与鉴权策略债务

级别：P2

- module registry 会保存 capability `timeout_seconds/max_attempts`，但 `call_capability()` 直接 await handler，不执行 contract timeout/retry。
- lifespan shutdown 对 event retry loop/model idle reaper 只调用 `.cancel()`，未 await 后台任务完成便停止 dispatcher 和 dispose DB。
- OCR、PDF render、model ensure 使用 `asyncio.to_thread`；上层 request/task timeout 不能立即终止已运行的同步线程。
- 登录失败计数是按用户名的进程内字典：5 次错误可定向锁定单个进程上的用户 15 分钟，多 worker/重启又可绕过计数。
- 多个文件创建、移动、删除、上传和回收站永久删除入口只要求 viewer。对象 owner 校验存在，但若 viewer 角色定义为只读，则属于垂直授权策略失配。
- 共享文件详情/目录列表会返回内部 `storage_path`。

这些问题建议分别进入 capability contract 执行、graceful shutdown、线程任务隔离、集中限流、角色权限矩阵、响应字段最小化的专项修复，不建议混为单一大改。

### 最近提交测试覆盖结论

最近 5 个 knowledge 核心提交没有为以下高风险行为补足自动化测试：

- 同一实体/同一 canonical 的并发认领和合并。
- 权威表不存在、缓存 miss、事务 aborted 后回退。
- 模型异常/低置信裁定进入人工复核。
- 图片重融后 page fusion、chunk、entity、graph 的版本一致性。
- 回滚脚本对锚点自有引用和多个变体的往返正确性。
- 因果层 `--limit`/`--rebuild` 的非破坏性。
- 分类 fallback 保持原类别。

这不是单纯“缺测试”问题：本轮已经在代码和数据中看到与上述缺口一致的孤儿边、断证据、空产出 done、并发/事务风险，因此应按回归修复测试处理。

### 第三轮修复优先级

1. 先封堵 read-share 写 ContentPackage，并清查 pipeline/resource/export 的同类写入口。
2. 立即给 relations 读取做 source/target owner + deleted 双端过滤；随后治理 185,920 条跨 owner 边和 1,961,618 条 deleted-document 边。
3. 停止单文档 graph rebuild 删除 owner 级共享节点；模型失败/空产出时保留旧结果并标 degraded/failed。
4. 修复 task lease/cancel/event retry 的副作用 fencing，避免旧 executor 与重领 executor 并发写业务表。
5. 为 graph node/edge/evidence 增加可落地的唯一性、FK 或等价约束；先制定 890 孤儿边、103 组重复节点、18,346 条断链 evidence 的迁移方案。
6. 暂停直接并行调用 `align_entity_batch` 和具有全量 delete 行为的临时治理脚本，完成 claim、参数上限、dry-run/journal 和回归测试后再运行。
7. 重构 stage 状态语义，清查 1,125 个 graph 空产出 done 和 10,856 个 profile done 无 active vector 文档。
8. 最后处理 execution contract 实际执行、graceful shutdown、集中登录限流、viewer 写权限和 storage path 响应最小化。

### 第三轮边界说明

- 本轮只执行只读 SQL、代码读取、日志读取和认证 GET/probe；没有调用写库治理能力，没有投递任务，没有重启服务。
- 唯一计划内文件变更是追加本报告。
- 工作区同时存在其他 agent 产生的临时文档删除、历史目录新增和 `审计报告_dp4_20260716.md`；本轮没有覆盖、回退或整理这些外部变更。
- `scripts/create_market_sales_word.py` 是会话开始前已存在的 untracked 文件，本轮未触碰。
