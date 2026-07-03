---
name: "terminal-tools r2 sweep boundary and file bridge hardening"
type: "task"
tags: [terminal-tools, module-sweep, r2, workspace-boundary, path-sanitize, false-success, verification]
agent: "codex-terminal-tools-sweep-20260703-r2"
created: "2026-07-03T07:02:12.684256+00:00"
---

# 改了什么

- 扫描 `modules/terminal-tools` 的 workspace boundary、path sanitize、command blocklist、timeout/output cap、publish/import、run_python/chart、fake-success 和 sandbox 覆盖。
- 修复 HTTP 调试端点失败时返回 `ApiResponse(success=False)` 的 200 假失败口径，改为抛 `ValidationError` 走统一错误响应。
- capability handler 增加防御性参数解析：坏 `timeout` 回默认值，坏 `file_id` / `folder_id` / `input_files` 返回结构化失败，避免跨模块调用直接冒 500。
- `_check_path_escape` 改为 punctuation-aware shell token 解析，能拦截 `echo ok; cat /etc/passwd`、`cmd|wc /etc/passwd` 这类复合命令后段路径逃逸。
- `list_workspace` 使用 `follow_symlinks=False`，返回 `is_symlink`，避免工作区内 symlink 泄露外部目标元数据。
- `publish`、`import`、`run_python` 图表上传从整文件 `read_bytes/write_bytes` 改成文件句柄/`copyfileobj` 流式处理。
- 清理 `sandbox.py` 未使用的工作区 base 死代码；前端能力展示补齐 `run_python` 和 `chart`。
- sandbox 测试新增复合命令逃逸和 symlink listing 契约。

# 问题清单

- P1: HTTP 端点失败走外层 200 + `success:false`，不符合统一异常契约。
- P1: `list_workspace` 跟随 symlink 取 stat，可能泄露工作区外目标元数据。
- P1: path escape 只看第一个命令，复合命令后段的 `cat /etc/passwd` 类逃逸靠后续 sandbox/command_safety 兜底，不够准。
- P2: publish/import/chart 上传整文件读入内存，和大文件/输出上限策略不一致。
- P2: capability 参数绕过 Pydantic 时坏整数可变 500。
- P3: `run_python` Pydantic 默认列表可变；前端背景页漏列两个已注册能力；sandbox 有覆盖缺口。

# 验证了什么

- `ruff check` via MCP lint: passed for all touched Python files.
- `python3.14 -m py_compile` for touched Python files: passed.
- `python3.14 modules/terminal-tools/sandbox/test_module.py`: passed.
- `run_test modules/terminal-tools/sandbox/test_module.py`: 7 passed.
- 活系统 `call_capability`: `write_file`/`read_file`/`list_workspace` succeeded; `read_file ../../etc/passwd` returned 422; `exec sudo whoami` returned 422; `exec echo ok; cat /etc/passwd` returned 422; cleanup `exec rm -f codex_terminal_sweep_r2.txt` succeeded and follow-up list confirmed test file removed.
- `probe /api/terminal-tools/health`: success true.
- `probe /api/health`: success true, worker running, module_errors null.
- `tail_log backend`: empty output.
- `git diff --name-only -- modules/terminal-tools`: only terminal-tools files.

# 残留风险

- 共享工作区有并行 worker 的 dirty 文件和 data/uploads，`finish_task/worktree_guard` 因全局 dirty 报红；本 worker 没有修改 `backend/app`、`frontend/src` 或其他模块。
- `exec`/`run_python` 当前仍要求 macOS `sandbox-exec`；Linux 仍 fail-closed。本次只修正误导性 bubblewrap 文案，没有新增 Linux sandbox 实现。

# 关联 commit

- 未提交；主会话统一验收后提交。
