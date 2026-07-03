---
name: "OpenCode sidecar 调研续补与 headless 工具链加固"
type: "task"
tags: [opencode, dev-toolkit, sidecar, pty, dispatch]
agent: "codex"
created: "2026-07-03T03:47:15.019858+00:00"
---

# 改了什么

继续核实 OpenCode Desktop sidecar 直连方案：确认桌面端 sidecar 使用 Basic Auth，username 为 opencode，password 来自主进程发给 sidecar worker 的 command.password，并在 sidecar 内写入 OPENCODE_SERVER_PASSWORD；密码不落盘、端口动态，因此不建议把桌面 sidecar 作为生产控制面。

工具台方向收敛到固定 headless 55891，并加固 dev_toolkit/opencode_tools.py：opencode serve 不再套 script，避免 MCP stdio/日志污染；后台 dispatch_letter 关闭 stdin 并在启动后检查进程是否立即退出；PTY read/stop 增加退出前后 drain，减少短 prompt 输出丢失。补充 dev_toolkit/test_opencode_tools.py 覆盖后台 stdin 和 serve command。

# 验证了什么

- python3.14 -m pytest dev_toolkit/test_opencode_tools.py：5 passed
- backend/.venv/bin/ruff check dev_toolkit/opencode_tools.py dev_toolkit/test_opencode_tools.py：All checks passed
- opencode_gateway_status：127.0.0.1:55891 正在监听，opencode 1.17.13

# 残留风险

当前 Codex MCP 进程需要重启后才会加载 opencode_tools.py 最新实现；工作区已有大量未提交/未跟踪文件，本轮未处理其它业务改动。
