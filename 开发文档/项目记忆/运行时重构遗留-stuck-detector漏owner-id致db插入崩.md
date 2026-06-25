---
name: "运行时重构遗留: stuck_detector漏owner_id致DB插入崩"
type: gotcha
tags: ["agent", "runtime", "stuck_detector", "gotcha", "verification"]
created: 2026-06-25
agent: claude
---

Agent升级02运行时骨架重构后, stuck_detector改成DB持久化(agent_stuck_rounds表)。但 _save_history 的 pg_insert 漏设 owner_id, 而该表 owner_id NOT NULL → agent一旦真做工具调用就 NotNullViolation, 表长期0行(stuck防死循环安全网自重构起一直瘫)。执行agent报告没抓到(它只发简单对话没进工具循环)。小马仔真数据验收(单测+查表行数+读调用点)抓出。修: detect_stuck(db, owner_id, ...) 和 _save_history(db, conv_id, owner_id, history) 加 owner_id, runtime tool_loop_runtime.py 两个调用点传 self.owner_id, test_stuck_detector.py 改 async+真DB(AsyncSessionLocal, OWNER_ID=4, 唯一session_key隔离+reset清理)。教训: 引擎状态搬到DB持久化时, 凡 {key}_* 表 owner_id NOT NULL 都要确认插入路径设了 owner_id; 简单对话验不出工具循环里的bug, 要么真触发工具要么查表行数。
