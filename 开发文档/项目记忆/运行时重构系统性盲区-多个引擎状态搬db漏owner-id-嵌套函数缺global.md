---
name: "运行时重构系统性盲区:多个引擎状态搬DB漏owner_id+嵌套函数缺global"
type: gotcha
tags: ["agent", "runtime", "owner_id", "integrity", "gotcha", "log_errors"]
created: 2026-06-25
agent: claude
---

运行时骨架重构(02)把多个引擎状态从内存搬到DB持久化, 埋了一类系统性bug, 04验收时log_errors连抓2个(加之前03抓的stuck共3处):
①owner_id漏插: agent_stuck_rounds / agent_budget_states 的 owner_id 是 NOT NULL, 但 _save_history/_save_to_db 的 pg_insert 没设 owner_id → 每次工具调用就 IntegrityError(NotNullViolation), 被try/except吞成日志, 功能(stuck防循环/budget递减追踪)实际全瘫、产物表0行。修法统一: detect_stuck/record_round/_save_to_db 加 owner_id 参数, runtime调用点传 self.owner_id, 对应test改签名(owner_id=4或0)。
②嵌套函数缺global: post_turn_hooks._maintenance_loop 里对模块全局 _background_maintenance_run_count 做 += 但嵌套函数没声明 global → UnboundLocalError每轮崩, 后台维护(review/画像/蒸馏)受影响。修:函数内加 global 声明。
排查法: SQL查 information_schema 列出所有 owner_id IS NOT NULL 的 {key}_* 表, 逐个核对应insert路径有没有设owner_id。
工具固化: dev_toolkit新增 log_errors(module) 专扫这类被吞的异常(Traceback/Violation/IntegrityError), AGENTS.md加'产物验证铁律'(后台/异步功能做完必 log_errors + 查产物表行数)。这3个bug都是log_errors照出来的。关联 [[运行时重构遗留-stuck-detector漏owner-id致db插入崩]] [[学习闭环review-fork调gateway错参致全程不产proposal]]。
