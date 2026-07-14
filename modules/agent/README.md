# agent — AI 助手

AI assistant module for conversations, tool use, workflow traces, profiles, skill governance, and multi-agent orchestration.

## 对外能力

| 能力 | 说明 |
|------|------|
| `activate_tool_guide` | 激活工具指引或晋升候选 |
| `classify_and_degrade` | 分类工具错误并返回降级建议 |
| `cleanup_demo_workflows` | 清理 Agent workflow demo 数据 |
| `create_workflow` | 创建 Agent 用户级工作流任务账本 |
| `disable_tool_guide` | 禁用工具指引 |
| `finalize_workflow` | 根据验证结果裁判 Agent 工作流终态 |
| `get_enterprise_profile` | 获取企业画像 |
| `get_enterprise_prompt` | 获取企业提示词 |
| `get_multi_agent_summary` | 汇总 Agent 工作流子代理/步骤执行结果 |
| `get_my_profile` | 获取个人用户画像 |
| ... | 等 43 个能力 |

## 接口

后端前缀：`/api/agent`

| 路径族 | 方法 |
|------|------|
| /admin | GET/POST |
| /chat | POST |
| /configs | DELETE/GET/POST/PUT |
| /conversations | DELETE/GET/PATCH/POST |
| /enterprise-prompt | GET/PUT |
| /health | GET |
| /profiles | GET |
| /prompts | DELETE/GET/POST/PUT |
| /render-tool-guidance | POST |
| /system-prompt | GET/PUT |
| /tool-guides | GET/POST |
| /tools | GET |
| /user-profile | GET |
| /workflows | GET/POST |

## 数据表

| 表名 |
|------|
| `agent_approval_queue` |
| `agent_checkpoints` |
| `agent_configs` |
| `agent_context_compactions` |
| `agent_context_snapshots` |
| `agent_conversations` |
| `agent_enterprise_profiles` |
| `agent_enterprise_prompt` |
| `agent_events` |
| `agent_failure_diagnostics` |
| `agent_failure_records` |
| `agent_market_profiles` |
| `agent_message_meta` |
| `agent_messages` |
| `agent_profile_signals` |
| `agent_prompts` |
| `agent_review_results` |
| `agent_review_tasks` |
| `agent_role_profiles` |
| `agent_skill_approvals` |
| `agent_skill_provenance` |
| `agent_skill_registry` |
| `agent_skill_usage` |
| `agent_system_prompt` |
| `agent_tool_calls` |
| `agent_tool_guide_candidates` |
| `agent_tool_guide_versions` |
| `agent_tool_guides` |
| `agent_trajectory_records` |
| `agent_usage_daily` |
| `agent_user_profile` |
| `agent_verification_results` |
| `agent_workflow_artifacts` |
| `agent_workflow_runs` |
| `agent_workflow_steps` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/agent/sandbox/test_module.py
cd modules/agent/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module agent --check
```
