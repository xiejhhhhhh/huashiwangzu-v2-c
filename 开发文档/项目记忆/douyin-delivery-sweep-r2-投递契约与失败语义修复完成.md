---
name: "douyin-delivery sweep r2 投递契约与失败语义修复完成"
type: "task"
tags: [douyin-delivery, module-sweep, r2, delivery-contract, db-audit, cleanup, validation, task_id:douyin-delivery-sweep-20260703-r2]
agent: "codex-douyin-delivery-sweep-20260703-r2"
created: "2026-07-03T07:26:50.669241+00:00"
---

本次只修改 modules/douyin-delivery/** 和项目记忆。修复内容：新增 douyin_accounts、douyin_materials、douyin_delivery_tasks 三张模块自有表；补账号/素材/投递任务 CRUD 与 /delivery-tasks/{id}/status；新增 create_delivery_task、mark_task_failed、cleanup_marked_data 能力并同步 manifest public_actions/db_migration_declaration；现有产品/脚本/文案/计划/提示词写入增加 channel/status/ad_type/budget_type/必填字段校验；投递任务 failed 必须带 error_message 并写 finished_at；cleanup 改为 editor 可按至少 6 字符 marker 清理当前用户测试数据。验证：ruff 全通过；sandbox pytest 9 passed；后端重启后 /api/health ok；routes/capabilities 可见新增契约；活栈写入 product/account/material/campaign/ad-copy 和 delivery task 成功，mark_task_failed 写入 failed/error_message/finished_at；非法 channel 和 failed 无 error_message 均返回 success:false 422；cleanup_marked_data 清理 r2-douyin-20260703 测试数据，总计先删 5 行、补修后再删 campaign 1 行；db_reverse_audit 最终 8 张 douyin 表中仅默认 prompts=7 与既有 scripts=1 非空；frontend npm run build 通过且未留下 frontend/src diff。残留风险：账号/素材/任务目前提供后端与 typed API helper，未新增 UI tabs；全仓仍有其他 worker 的 unrelated dirty/data uploads，finish_task 因此报告全局边界 false，但本任务 forbidden_hit_count=0。关联 commit：未提交。
