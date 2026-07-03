---
name: "调研-OpenCode桌面端Sidecar协议与直连可行性"
type: "task"
tags: [opencode, sidecar, auth, gateway, research]
agent: "opencode"
created: "2026-07-03T03:41:32.646470+00:00"
---

## 结论

**不建议直连桌面 sidecar。继续使用 headless 55891 网关是正确的、稳定的方案。**

## 关键发现

1. Desktop sidecar (端口动态变化, 当前53898) 使用 Basic Auth, username=`opencode`, password=`randomUUID()`/startup
2. 密码通过 Electron IPC 传入子进程, 在 `process.env.OPENCODE_SERVER_PASSWORD` 中, 进程外不可见
3. 密码未持久化到任何文件 (global.dat/workspace.dat/Cookies/Local Storage 均无)
4. sidecar 端口每次桌面重启随机分配 (历史值: 55813/50870/53898/62974 等)
5. `opencode run --attach` 原生支持 `--password`/`--username` 参数, 但密码无法从外部获取
6. Headless 55891 无认证, 固定端口, `opencode run --attach` 直连成功
7. 两者底层同一 `Server.listen()` 代码, API 能力完全等同

## 推荐

继续使用 headless 55891。MCP → mailbox → dispatch_letter → agent 整条链路已通过测试, 运行稳定。Desktop sidecar 没有额外能力, 接入成本高且不可靠。

## Codex 补充核实与工具台修正

2026-07-03 继续核实：

- `sidecar.js` 中 `Server.listen({ username: "opencode", password: command.password })` 与 `prepareSidecarEnv()` 明确把密码写入 `OPENCODE_SERVER_PASSWORD`。
- 密码来自 Electron 主进程发给 sidecar worker 的 `command.password`，外部只能看到动态端口和 Basic Auth challenge，看不到密码明文。
- 因此桌面 sidecar 不是“协议未知”，而是“认证材料不可稳定取得”；除非 OpenCode 桌面端未来公开 attach token，否则不应把它作为生产控制面。
- 已将工具台方向收敛到固定 headless 55891：去掉 `opencode serve` 的 `script` 包装，避免 MCP stdio/日志混入控制字符和 JSON-RPC；后台 `dispatch_letter` 关闭 stdin 并在启动后检查子进程是否立即退出；PTY `read/stop` 增加退出前后最后 drain，减少短 prompt 输出丢失。

验证：

- `python3.14 -m pytest dev_toolkit/test_opencode_tools.py`：5 passed
- `backend/.venv/bin/ruff check dev_toolkit/opencode_tools.py dev_toolkit/test_opencode_tools.py`：All checks passed

## 调研依据

- asar 解压分析: `out/main/sidecar.js` + `out/main/index.js`
- 实机验证: 9 条 curl/lsof/ps/opencode 命令
- 存储介质排查: 5 种 (global.dat, workspace.dat, Cookies, Local Storage, process env)
