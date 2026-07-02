---
name: "db-backtrace-r2节点2-六表反向审计初判"
type: "task"
tags: [db-backtrace, db-reverse-audit, agent, memory, image-gen, codemap, 20260703]
agent: "db-backtrace-worker-r2"
created: "2026-07-02T16:15:02.478389+00:00"
---

节点2：db_reverse_audit + db_schema + capabilities + routes + CodeGraph 初判。
- agent_configs：0 行，有 /api/agent/configs CRUD 与 AgentConfigPanel 管理 UI；代码里 action_policy/context_pipeline 只读取并回退默认策略，空表不致主链路失败，但管理台会显示空配置，需要继续确认是否应 seed 默认 agent 配置。
- agent_skill_usage：0 行，有 SkillUsage 模型和 record_skill_usage()，但 CodeGraph 只显示函数本身，未发现运行链路调用，疑似治理记录函数未接入真实 skill 注入/执行路径。
- memory_experiences：0 行，memory 模块注册 save_experience/match_experience/experience_feedback，agent engine 通过跨模块能力调用，不直读表。空表可预期，但若 agent 成功任务没有落经验才是断链，需看 task_sink。
- memory_links：0 行，仅 dream/链图类流程产生，属于可选派生链路，当前空不直接判 bug。
- imagegen_records：0 行，generate 成功后应记录，usage_history 读此表；空表可能只是新库未生成，需用 list_templates/usage_history 只读验证，不直接触发真实生图。
- codemap_feedback：0 行，report_inaccuracy/list_feedback 完整；这是人工反馈表，空表可接受。
