---
name: "douyin codemap imagegen 空链路只读审计 r3"
type: "task"
tags: [audit, douyin-delivery, codemap, image-gen, db-reverse-audit, r3]
agent: "codex-douyin-codemap-imagegen-flow-audit-r3"
created: "2026-07-03T10:49:55.374689+00:00"
---

# 做了什么
只读审计三条疑似空链路：douyin-delivery 投放主链、codemap_feedback 反馈闭环、imagegen_records 成本记录。未改产品代码，未 commit/push；未触发 report_inaccuracy/create_delivery_task/generate 等写入或外部成本动作。

# 关键证据
- 工具台流程：brief、plan_task(investigation)、worktree_guard、code_explore、routes、capabilities、db_schema、db_reverse_audit、probe、call_capability、tail_log、finish_task 均已执行。
- douyin DB：douyin_prompts=7(owner_id=0)、douyin_scripts=1(owner_id=1)、douyin_delivery_tasks=1(owner_id=3)，products/ad_copies/campaigns/accounts/materials=0；当前 admin 用户 id=4，因此活栈 GET products/scripts/ad-copies/campaigns/accounts/materials/delivery-tasks 均返回 []。现有 delivery task payload marker 为 r2-douyin-json-20260703，疑似测试残留。
- douyin 源码：accounts/materials/delivery_tasks 是 owner-scoped CRUD/status；create_delivery_task 只插入 DouyinDeliveryTask，没有 register_task_handler 或巨量/千川/本地推外部投放适配器。README 写业务流程“产品/卖点→选择渠道/账号/素材→AI生成→校验→保存草稿→投放计划→投递任务状态”，但代码只覆盖内容生成、CRUD、状态登记。
- codemap DB：codemap_feedback=0，codemap_metrics=1；capability/HTTP report_inaccuracy 会写 CodemapFeedback，list_feedback 可读空列表，stats 返回 feedback_count=0、empirical_accuracy=100、query_count=5。结论是反馈入口存在但需要人工/agent 主动调用，当前流程没有自动在 codegraph/codemap 不准时落反馈；README 的守卫要求 report 后清理测试反馈，历史记忆也显示测试反馈已清理。
- image-gen DB：imagegen_records=0，framework_file_items 无 image-gen_% 文件；list_templates 显示 liblib-star3/gptstore/placeholder 均 available，usage_history 返回 records=[]。源码在 RuntimeError、unexpected error、无可用图片、成功/partial 后都会 _save_record；验证/空 prompt 前置失败不记录。历史“实测可用/成本记表”与当前 0 行更像当前库切换、清理或验证后删除记录，不是源码完全断链；但当前库没有可复核历史成本数据。

# P0/P1/P2
P0：douyin-delivery 完整投放链不可达/未实现（不是仅空数据）：无真实投放 worker、无外部平台适配器、delivery task 只是 CRUD/status。
P1：codemap_feedback=0 是反馈闭环依赖人工调用导致的运营/流程断链风险；功能存在但不产数会使 empirical_accuracy 长期假满分。
P1：imagegen_records=0 与历史“成本落库”叙述在当前库不一致；代码路径存在，但没有当前库证据证明真实 Liblib/GPTStore 生成曾落库。
P2：douyin 当前可见业务数据为零，系统默认 prompt owner_id=0 可见，另有 owner_id=1/3 的脚本/测试任务对当前 admin id=4 不可见，容易误判为“有数据”。

# 建议 worker 拆分
1. douyin-delivery-flow-worker：只在 modules/douyin-delivery 内补投放执行 worker/平台适配器抽象/任务消费闭环，或明确改名为“内容与计划助手”避免承诺真实投放。
2. codemap-feedback-loop-worker：补 agent/tooling 在发现 codemap 不准时的自动/半自动 report_inaccuracy 通路，并设计测试反馈自动清理。
3. imagegen-ledger-verification-worker：使用 placeholder 或低成本真实模板执行一次 generate→history→DB→文件清理的可复现验收，确认记录链路；如要验证 Liblib 成本，必须带预算和清理策略。

# 关联 commit
无。本次只读审计，无提交。
