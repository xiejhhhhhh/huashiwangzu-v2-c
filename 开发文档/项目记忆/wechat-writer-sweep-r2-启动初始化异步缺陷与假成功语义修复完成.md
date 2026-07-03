---
name: "wechat-writer sweep r2：启动初始化异步缺陷与假成功语义修复完成"
type: "task"
tags: [wechat-writer, module-sweep, r2, async-init, validation, false-success, sandbox, task_id:wechat-writer-sweep-20260703-r2]
agent: "codex-wechat-writer-sweep-20260703-r2"
created: "2026-07-03T07:35:59.599236+00:00"
---

完成 modules/wechat-writer 模块级扫雷与修复。核心发现：backend/init_db.py 原 `_run_startup_init = _init_db` 为同步入口，内部两次 `asyncio.run()`；当模块在已有 event loop 中导入/自愈加载时会触发 RuntimeWarning coroutine was never awaited，并且异常被 warning 吞掉后可能导致建表/默认 prompt 种子没有执行。修复：拆出 `ensure_wechat_tables()`、`seed_default_prompts()`、`run_init()`；`_run_startup_init()` 使用 `asyncio.get_running_loop()` 判断，running loop 下 `loop.create_task(run_init())` 并用 done_callback 记录异常，无 loop 时才 `asyncio.run(run_init())`。同时修复服务层假成功/边界：空 direction/topic/outline/content 和非法 draft status 直接 `ValidationError`；模型网关返回 error 时抛 `AppException(status_code=502)`，不再外层 success 但内容空；`generate_topics` 注解改为 dict，`generate_article` 使用 manifest 声明的 direction 作为提示词补充；SQLAlchemy false 比较改为 `.is_(False)`。router 清理历史未用 import，`resolve_user_id` 直接从框架公共服务导入。sandbox/test_module.py 新增 3 个真测：running event loop 中启动初始化只调度可 await task、不调用 asyncio.run；空生成输入在 DB/模型前失败；网关 error 不假成功。验证：ruff 四个 Python 文件 All checks passed；`PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modules/wechat-writer/sandbox/test_module.py -q` 9 passed；工具台 run_test 同样 9 passed；活系统 `/api/health` ok，`GET /api/wechat-writer/drafts?page=1&page_size=1` 返回统一响应 success true。活系统 `wechat-writer:generate_topics` 空参数探针因常驻后端尚未加载本次代码且连接断开，未作为新逻辑验收；需要主会话重启后端后再复测 warning 是否消失与空参数 422。未创建业务测试数据。边界：本任务产品改动限定在 modules/wechat-writer/；项目记忆写入本任务两条。worktree_guard 仍因并发 worker 在 data/uploads、docs-open、im、media-intelligence 等已有改动报红，未触碰或整理。
