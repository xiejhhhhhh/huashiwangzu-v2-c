---
name: "desktop-tools sweep r2 修复与验证完成"
type: "task"
tags: [desktop-tools, module-sweep, r2, verification, task_id:desktop-tools-sweep-20260703-r2]
agent: "codex-desktop-tools-sweep-20260703-r2"
created: "2026-07-03T07:19:52.694639+00:00"
---

完成 desktop-tools r2 扫雷。改动文件：modules/desktop-tools/backend/router.py、modules/desktop-tools/manifest.json、modules/desktop-tools/README.md、modules/desktop-tools/sandbox/test_module.py。核心修复：read_file 失败路径改为抛统一异常，避免假成功；read_file 输出增加 20000 chars / 80 blocks 截断与 limits 元数据；list_files/search_files 增加 page/page_size 守卫和真实 total；文件名/扩展名/ID 参数统一校验，拒绝路径形态；manifest background-service component_key 置空；README 同步 15 个能力；sandbox 从内联假测改成真实导入 router/registry 的合约测试。验证：ruff 通过；PYTHONPATH=backend backend/.venv/bin/python modules/desktop-tools/sandbox/test_module.py 通过；finish_task 内置 pytest 4 passed；活系统 /api/health 200，desktop-tools:list_files 成功，search_files page_size=101 和 read_file file_id=0 均返回统一 422；backend tail_log 空。未创建测试数据，避免共享活栈留下文件/回收站记录。finish_task 因全仓存在其他 worker dirty 文件和项目记忆路径不在其 module-only allowed_prefix 内返回 success=false；单独 worktree_guard forbidden_hit_count=0，本 worker 未碰 terminal-tools/browser-tools/backend/app/frontend/src/其他 modules。关联 commit：未提交。
