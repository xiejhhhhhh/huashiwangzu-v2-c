# terminal-tools — Agent 终端工具模块

为 Agent 提供**受边界约束的终端执行能力**:在每用户独立的工作区里跑命令/写脚本/处理数据，成果显式交付到框架文件系统（桌面可见），临时文件自动清理。

## 定位

Agent 的"通用兜底能力":模块没覆盖的（跑脚本、算数据、批处理），用终端搞定。

## 两套世界分离

| Agent 行为 | 走的技能 | 指向 |
|-----------|---------|------|
| 读用户文件/桌面感知 | `desktop-tools:*`（框架文件系统） | 框架虚拟文件系统,**非宿主机** |
| 执行命令/跑脚本 | `terminal-tools:*`（本模块） | `data/workspaces/{user_id}/` 工作区,**非宿主机其他路径** |
| 工作区↔框架文件互通 | `terminal-tools:publish` / `import` | 显式桥接两套世界 |

CLI 的 cwd 永远锁死在该用户工作区，它眼里的"文件/当前目录"就是工作区内的，碰不到宿主机真实桌面。

## 已注册能力（6 个）

| 能力 | 说明 | min_role |
|------|------|----------|
| `terminal-tools:exec` | 在用户工作区执行 shell 命令，返回 stdout/stderr/退出码 | editor |
| `terminal-tools:write_file` | 写文件到工作区 | editor |
| `terminal-tools:read_file` | 读工作区文件 | viewer |
| `terminal-tools:list_workspace` | 列工作区文件 | viewer |
| `terminal-tools:publish` | 把工作区文件交付到框架文件系统（桌面可见） | editor |
| `terminal-tools:import` | 把框架文件拷进工作区供 CLI 处理 | editor |

## 安全边界

### 1. 路径约束（核心安全机制）
- 所有文件操作（write/read/list/publish/import）的文件路径参数，必须先经过 `_resolve_workspace_path()` 规范化+resolve，再检查 resolve 后的绝对路径是否以工作区根目录开头。
- 越界路径（绝对路径如 `/Users/...`、`~`、`../` 逃逸、symlink 逃逸）一律拒绝，返回错误信息。
- 工作区根: `backend/data/workspaces/{user_id}/`，按 `user_id` 隔离，用户间互不可见。

### 2. 危险命令拦截（exec 前置检查）
- 黑名单匹配: `sudo`、`su`、`shutdown`、`reboot`、`halt`、`poweroff`、`mkfs`、`dd if=`、`fdisk`、`parted`、`mount`、`umount`、`rm -rf /`、`passwd`、`visudo`、`chown ... /`、`chmod 777 /`、fork 炸弹模式。
- 匹配即拦截，返回错误信息，不创建子进程。

### 3. 资源限制
- 超时: 默认 60s，最大 600s。`subprocess.run(timeout=...)` 硬超时。
- 输出截断: stdout/stderr 各最大 1MB，超出部分截断并加标记。
- `HOME` 和 `WORKSPACE` 环境变量重定向到工作区目录。

### 4. CWD 锁定
- 所有命令的 cwd 固定为该用户工作区根目录。

### 隔离强度
**本地执行 + 应用层约束 = "约束 + 信任同事"**，适合局域网内部场景。
不是 Docker 级强隔离，懂行者理论上可绕过（如写 C 程序直接 syscall）。
将来需要更强隔离再上受限用户/Docker。

## 产物策略:草稿区 + 显式交付

- **工作区 = 草稿区**:Agent 在里面自由读写（临时脚本、中间产物），**默认不进框架文件系统、不上桌面**。
- **显式交付**:Agent 完成任务，主动 `publish` 成果文件 → 框架文件系统 → 用户桌面可见。
- **导入**:Agent 可 `import` 框架文件进工作区，用 CLI 工具处理后再 `publish` 回去。
- **临时清理**:当前由 Agent 脚本自行清理临时文件；将来可加后台定时清理任务（超时 24h / 超大小 500MB 自动清）。

## 模块结构

```
modules/terminal-tools/
├── manifest.json          # 模块身份声明 + public_actions
├── README.md              # 本文档
├── backend/
│   └── router.py          # FastAPI router + 6 个 register_capability
├── frontend/
│   └── index.vue          # 最简前端入口
├── runtime/
│   └── index.ts           # Runtime SDK（从 _template 复制）
└── sandbox/               # 独立开发环境（从 _template 复制）
```

## 验证

```bash
# 边界守卫
git diff --name-only  # 应仅在 modules/terminal-tools/ + .gitignore

# 框架测试
cd backend && .venv/bin/python -m pytest

# 技能注册确认
curl /api/modules/capabilities | grep terminal-tools
```

## 边界验证清单

- [x] exec 在工作区跑命令正常
- [x] 越界路径（cat /Users/...、cd / 后操作）→ 被拒绝
- [x] 危险命令（sudo、rm -rf /）→ 被拦截
- [x] 超时命令（sleep 999）→ 被超时终止
- [x] publish 后文件出现在框架文件系统
- [x] import 后框架文件出现在工作区
- [x] owner 隔离: 用户只能操作自己的工作区
