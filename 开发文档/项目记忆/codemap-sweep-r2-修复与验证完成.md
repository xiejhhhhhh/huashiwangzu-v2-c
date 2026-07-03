---
name: "codemap sweep r2 修复与验证完成"
type: "task"
tags: [codemap, module-sweep, locks, index, confidence, feedback, verification, task_id:codemap-sweep-20260703-r2]
agent: "codex-codemap-sweep-20260703-r2"
created: "2026-07-03T07:04:19.559820+00:00"
---

完成 codemap sweep r2。修复：1) graph 增加 index_status/index_empty/build_error，空扫描或无成功解析不再 ready，confidence 归 0，health/query ready 错误区分 building 与 unavailable；2) indexer 不再吞 read/syntax parse 失败，_parse_file 真实 record_file_fail，parse_fail_count/stale/reliability_note 可信；3) locks.json 读损坏/格式异常 fail-closed，写入 temp+rename 前 fsync 文件并尝试 fsync 目录，check/list 的过期清理写失败不再假成功，越界 check_lock 返回 success:false；4) 新增 validation.py 统一 report_inaccuracy path/query_type 校验，HTTP 和 capability 都拒绝空 path、空/超长 query_type、越界路径；5) 清理 codemap 内 ruff import 问题；6) tests 增加空索引、parse failure、锁损坏 fail-closed、反馈校验覆盖。验证：ruff 全 codemap Python 文件 passed；modules/codemap/tests/test_codemap.py 57 passed；modules/codemap/sandbox/test_module.py 18 passed；活系统 /api/health ok，codemap:stats/get_file ok，impact missing/check_boundary empty/check_lock 越界/report_inaccuracy 空 path 均 success:false；acquire_lock 后 release_lock 并 check_lock locked:false，未残留测试锁。边界：自身代码改动只在 modules/codemap/**，项目记忆按要求写入；全局 worktree_guard 因其他 worker 和 data/uploads 并行改动仍报红。
