---
name: "start_backend restart 多 worker 可能杀不到 uvicorn 父进程"
type: "gotcha"
tags: [backend, watchdog, restart, multi-worker, gotcha]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:47:17.021420+00:00"
---

2026-07-03 主会话验收 pdf-parser 时发现：执行 scripts/start_backend.sh --restart 后端口 33000 仍由旧 uvicorn worker 占用，日志继续显示旧代码路径。原因是 start_backend.sh 的 backend_pids() 只取 lsof 返回的 head -1，可能拿到 multiprocessing worker，其 command 不是 uvicorn app.main:app，导致未识别/未杀 uvicorn 父进程。手工 kill uvicorn 父进程 93957 和 listen worker 后，再运行 start_backend.sh --restart 才真正换成新 PID，新代码生效。建议后续框架任务修复 backend_pids：枚举全部 listen PID，向上找 PPID/command/cwd，杀 uvicorn 父进程及其子进程。
