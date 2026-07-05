# agent — AI 助手

## Responsibility

AI assistant module for conversations, tool use, workflow traces, profiles, skill governance, and multi-agent orchestration.

## Manifest Contract

<!-- DOCS-SYNC: section=manifest -->
| Field | Value |
|---|---|
| key | `"agent"` |
| name | `"AI 助手"` |
| category | `"AI"` |
| window_type | `"normal"` |
| singleton | `true` |
| allow_multiple | `false` |
| show_in_launcher | `true` |
| show_on_desktop | `true` |
| route_prefix | `"/api/agent"` |
| backend.enabled | `true` |
| backend.router | `"backend/router.py"` |
| actual backend prefix | `/api/agent` |
<!-- /DOCS-SYNC -->

## Current Capabilities

- Desktop behavior, format binding, window behavior, and permissions are declared in `manifest.json`.
- Backend HTTP behavior, if present, is implemented in `backend/router.py`.
- Runtime module calls, if present, are declared in `manifest.public_actions` and registered by backend capability code.

## HTTP API / Endpoint Families

Backend HTTP prefix: `/api/agent`

| Family | Methods | Purpose |
|---|---|---|
| `admin` | GET/POST | Endpoint family under `/api/agent` |
| `chat` | POST | Endpoint family under `/api/agent` |
| `configs` | DELETE/GET/POST/PUT | Endpoint family under `/api/agent` |
| `conversations` | DELETE/GET/PATCH/POST | Endpoint family under `/api/agent` |
| `enterprise-prompt` | GET/PUT | Endpoint family under `/api/agent` |
| `health` | GET | Endpoint family under `/api/agent` |
| `profiles` | GET | Endpoint family under `/api/agent` |
| `prompts` | DELETE/GET/POST/PUT | Endpoint family under `/api/agent` |
| `render-tool-guidance` | POST | Endpoint family under `/api/agent` |
| `system-prompt` | GET/PUT | Endpoint family under `/api/agent` |
| `tool-guides` | GET/POST | Endpoint family under `/api/agent` |
| `tools` | GET | Endpoint family under `/api/agent` |
| `user-profile` | GET | Endpoint family under `/api/agent` |
| `workflows` | GET/POST | Endpoint family under `/api/agent` |

## Public Actions / Capability Contract

<!-- DOCS-SYNC: section=public_actions -->
Runtime authority: backend `register_capability(...)`. Discovery metadata: `manifest.public_actions`.

Total public actions: 42

| Action | min_role | Parameters | Purpose |
|---|---|---|---|
| `activate_tool_guide` | `admin` | `guide_id` | 激活工具指引或晋升候选 |
| `classify_and_degrade` | `viewer` | `error_class`, `exception`, `tool_result`, `user_input` | 分类工具错误并返回降级建议 |
| `cleanup_demo_workflows` | `admin` | `marker` | 清理 Agent workflow demo 数据 |
| `create_workflow` | `viewer` | `extra_meta`, `intent`, `owner_id`, `source`, `title` | 创建 Agent 用户级工作流任务账本 |
| `disable_tool_guide` | `admin` | `guide_id` | 禁用工具指引 |
| `finalize_workflow` | `viewer` | `developer_summary`, `run_id` | 根据验证结果裁判 Agent 工作流终态 |
| `get_enterprise_profile` | `viewer` | none | 获取企业画像 |
| `get_enterprise_prompt` | `admin` | none | 获取企业提示词 |
| `get_multi_agent_summary` | `viewer` | `run_id` | 汇总 Agent 工作流子代理/步骤执行结果 |
| `get_my_profile` | `viewer` | none | 获取个人用户画像 |
| `get_role_profile` | `viewer` | `role_key` | 获取岗位画像详情 |
| `get_role_profiles` | `viewer` | none | 列出岗位画像 |
| `get_system_prompt` | `admin` | none | 获取系统提示词 |
| `get_tool_guide` | `viewer` | `guide_id` | 获取单条工具指引详情 |
| `get_workflow_governance_summary` | `viewer` | none | 汇总 Agent workflow 治理面板统计 |
| `get_workflow_status` | `viewer` | `run_id` | 读取 Agent 工作流极简状态 |
| `list_market_profiles` | `viewer` | `profile_type` | 列出市场/品牌画像 |
| `list_profile_signals` | `viewer` | `applied`, `signal_type` | 查看画像信号 |
| `list_tool_guides` | `viewer` | `agent_code`, `owner_id`, `scope`, `status`, `tool_name` | 列出工具指引 |
| `list_trajectories` | `admin` | `conversation_id`, `session_id` | 查看执行轨迹 |
| `list_workflow_artifacts` | `viewer` | `run_id` | 列出 Agent 工作流产物元数据 |
| `list_workflow_steps` | `viewer` | `run_id` | 列出 Agent 工作流步骤账本 |
| `list_workflows` | `viewer` | `has_artifacts`, `has_failures`, `has_references`, `limit`, `offset`, `owner_id`, `status` | 列出当前用户或管理员可见的 Agent 工作流 |
| `propose_tool_guide` | `editor` | `acceptance_policy`, `agent_code`, `failure_policy`, `guide_text`, `scope`, `title`, `tool_name` | 提交候选工具指引 |
| `record_profile_signal` | `viewer` | `confidence`, `signal_data`, `signal_type`, `target_profile_type` | 记录画像信号 |
| `record_tool_call` | `viewer` | `action`, `approval_policy`, `arguments`, `idempotency_key`, `run_id`, `side_effect_level`, `step_id`, `target_module`, `tool_name` | 记录 Agent 工作流工具或 capability 调用 |
| `record_trajectory` | `viewer` | `conversation_id`, `session_id`, `user_input` | 记录执行轨迹 |
| `record_verification` | `viewer` | `is_required_for_completion`, `run_id`, `status`, `step_id`, `summary`, `verification_type` | 记录 Agent 工作流验证结果并参与终态裁判 |
| `record_workflow_step` | `viewer` | `extra_meta`, `run_id`, `status`, `step_key`, `summary`, `title`, `type` | 记录或更新 Agent 工作流步骤状态 |
| `render_tool_guidance` | `viewer` | `agent_code`, `max_tokens`, `tool_names` | 按合并顺序渲染当前工具指引 |
| `request_workflow_approval` | `viewer` | `decision_scope`, `request_type`, `resume_target`, `risk_level`, `run_id`, `tool_call_id` | 为 Agent 工作流创建可恢复的审批请求 |
| `resolve_workflow_approval` | `admin` | `approval_id`, `decision`, `payload_hash`, `reason` | 处理 Agent 工作流审批并恢复或终止对应 tool call |
| `rollback_tool_guide` | `admin` | `guide_id`, `version` | 回滚工具指引到指定版本 |
| `seed_demo_workflows` | `admin` | `cleanup_existing`, `marker`, `owner_id` | 创建可清理的 Agent workflow demo 数据 |
| `skill_manage` | `admin` | `action`, `allowed_tools`, `body`, `description`, `name`, `scope` | 管理技能（CRUD/审批/统计/追溯） |
| `spawn_subagent` | `viewer` | `context`, `conversation_id`, `gate_retry`, `gates`, `max_rounds`, `session_id`, `task`, `tasks`, `tools`, `track_trajectory`, `turn_index_offset`, `write_enabled` | 生成子 Agent 执行独立任务（支持批量/白名单/执行轨迹/Gate 校验） |
| `update_enterprise_prompt` | `admin` | `content` | 更新企业提示词 |
| `update_my_profile` | `viewer` | `profile_data` | 更新个人用户画像 |
| `update_system_prompt` | `admin` | `content` | 更新系统提示词 |
| `upsert_enterprise_profile` | `admin` | `business_rules`, `communication_style`, `enterprise_name`, `tone` | 创建/更新企业画像 |
| `upsert_market_profile` | `admin` | `attributes`, `key`, `name`, `profile_type`, `tags` | 创建/更新市场画像 |
| `upsert_role_profile` | `admin` | `allowed_tools`, `focus_areas`, `role_key`, `role_name`, `taboos`, `tone` | 创建/更新岗位画像 |
<!-- /DOCS-SYNC -->

## Data Ownership

| Table / Prefix | Purpose |
|---|---|
| `agent_approval_queue` | Owned by `agent` module |
| `agent_checkpoints` | Owned by `agent` module |
| `agent_configs` | Owned by `agent` module |
| `agent_context_compactions` | Owned by `agent` module |
| `agent_context_snapshots` | Owned by `agent` module |
| `agent_conversations` | Owned by `agent` module |
| `agent_enterprise_profiles` | Owned by `agent` module |
| `agent_enterprise_prompt` | Owned by `agent` module |
| `agent_events` | Owned by `agent` module |
| `agent_failure_diagnostics` | Owned by `agent` module |
| `agent_failure_records` | Owned by `agent` module |
| `agent_market_profiles` | Owned by `agent` module |
| `agent_message_meta` | Owned by `agent` module |
| `agent_messages` | Owned by `agent` module |
| `agent_profile_signals` | Owned by `agent` module |
| `agent_prompts` | Owned by `agent` module |
| `agent_review_results` | Owned by `agent` module |
| `agent_review_tasks` | Owned by `agent` module |
| `agent_role_profiles` | Owned by `agent` module |
| `agent_skill_approvals` | Owned by `agent` module |
| `agent_skill_provenance` | Owned by `agent` module |
| `agent_skill_registry` | Owned by `agent` module |
| `agent_skill_usage` | Owned by `agent` module |
| `agent_system_prompt` | Owned by `agent` module |
| `agent_tool_calls` | Owned by `agent` module |
| `agent_tool_guide_candidates` | Owned by `agent` module |
| `agent_tool_guide_versions` | Owned by `agent` module |
| `agent_tool_guides` | Owned by `agent` module |
| `agent_trajectory_records` | Owned by `agent` module |
| `agent_usage_daily` | Owned by `agent` module |
| `agent_user_profile` | Owned by `agent` module |
| `agent_verification_results` | Owned by `agent` module |
| `agent_workflow_artifacts` | Owned by `agent` module |
| `agent_workflow_recipes` | Owned by `agent` module |
| `agent_workflow_runs` | Owned by `agent` module |
| `agent_workflow_steps` | Owned by `agent` module |

Use `db_schema()` for live database details. This module must not directly read or write other modules' tables.

## Cross-Module Dependencies

- Manifest dependencies are declared in `manifest.json` when needed.
- Runtime calls to other modules must use framework capability calls, not imports or direct DB reads.

## File Access / Permission Boundary

If this module consumes `file_id`, it must validate file access through framework file access helpers or an approved public capability before reading disk.

## Frontend / Backend Structure

| Path | Status |
|---|---|
| `frontend/index.vue` | present |
| `runtime/index.ts` | present |
| `backend/router.py` | present |
| `sandbox/test_module.py` | present |
| `sandbox/package.json` | present |

## Acceptance

<!-- DOCS-SYNC: section=sandbox -->
| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `modules/agent/manifest.json` |
| Capability drift | PASS | `capability_contract_diff(module="agent", include_parameters=true)` |
| Backend sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/agent/sandbox/test_module.py` |
| Frontend sandbox | PASS | `cd modules/agent/sandbox && npm run build` |
| Matrix check | PASS | `backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module agent --check` |
| Known debt | PASS | None |
<!-- /DOCS-SYNC -->

## Reproducible Checks

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/agent/sandbox/test_module.py
cd modules/agent/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module agent --check
```

## Boundaries

- Keep module business code and data inside `modules/agent/`.
- Do not import other modules' internal code.
- Do not directly read or write other modules' tables.
- Promote common needs to framework tasks only when multiple modules need the same long-term public capability.
