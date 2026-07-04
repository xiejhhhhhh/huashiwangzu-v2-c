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

## 已注册能力（8 个）

| 能力 | 说明 | min_role |
|------|------|----------|
| `terminal-tools:exec` | 在用户工作区执行 shell 命令，返回 stdout/stderr/退出码 | editor |
| `terminal-tools:write_file` | 写文件到工作区 | editor |
| `terminal-tools:read_file` | 读工作区文件 | viewer |
| `terminal-tools:list_workspace` | 列工作区文件 | viewer |
| `terminal-tools:publish` | 把工作区文件交付到框架文件系统（桌面可见） | editor |
| `terminal-tools:import` | 把框架文件拷进工作区供 CLI 处理 | editor |
| `terminal-tools:run_python` | 在工作区执行 Python 代码（pandas/numpy/matplotlib），自动收集图表并上传框架文件系统 | editor |
| `terminal-tools:chart` | 傻瓜式出图（折线/柱状/饼图），传入数据自动出图并存入框架文件系统 | editor |

## 安全边界

### 1. 路径约束（核心安全机制）
- 所有文件操作（write/read/list/publish/import）的文件路径参数，必须先经过 `_resolve_workspace_path()` 规范化+resolve（基于 `app.core.workspace_security.resolve_workspace_path` + `app.core.path_security.validate_within_dir`），再检查 resolve 后的绝对路径是否在用户工作区内。
- 越界路径（绝对路径如 `/Users/...`、`~`、`../` 逃逸、symlink 逃逸）一律拒绝，返回简洁错误信息（不泄漏宿主机敏感路径）。
- 工作区根: `backend/data/workspaces/{user_id}/`，按 `user_id` 隔离，用户间互不可见。
- API 返回只暴露工作区相对路径，不返回 `absolute_path`。
- `publish.filename` 和框架文件默认导入名会折叠成单个安全文件名；显式 `import.target_path` 仍允许工作区内子目录，但必须通过同一套边界校验。

### 2. 危险命令拦截（exec 前置检查）
- 黑名单匹配基于 `app.core.command_safety.check_dangerous_command`（从 terminal-tools 本地模式迁移至框架公共 helper，并参考 Hermes 扩充了更多模式）。
- 覆盖: `sudo`、`su`、`shutdown/reboot/halt/poweroff`、`mkfs`、`dd if=`、`fdisk/parted`、`mount/umount`、`rm -rf /`、`passwd`、`visudo`、`chown ... /`、`chmod 777 /`、fork 炸弹、`curl/wget | sh`（pipe to shell）、写 `/etc/` 等。
- 匹配即拦截，返回错误信息，不创建子进程。不做审批/allowlist/YOLO 模式（统一拒绝）。

### 3. 资源限制
- 超时: 默认 60s，最大 600s。`subprocess.run(timeout=...)` 硬超时。
- 输出截断: stdout/stderr 各最大 1MB，子进程输出先写工作区临时文件再按上限读取，避免先把无限输出吃进内存。
- `read_file` 文本内容最多返回 1MB，超出时 `truncated: true`；二进制文件不返回内容正文。
- `list_workspace` 最多返回 1000 项，超出时 `truncated: true`。
- `HOME`、`WORKSPACE` 和 `TMPDIR` 环境变量重定向到工作区目录。

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
- `run_python` 每次运行使用 `.da_{run_id}` 临时目录，输入文件经 owner 校验后复制到该目录，结束后 `finally` 清理。
- `chart` 基于 `run_python`，如果 Python 返回成功但没有成功上传图表文件，会转为 `success:false`，避免假成功。

## 模块结构

```
modules/terminal-tools/
├── manifest.json          # 模块身份声明 + public_actions（6 个基础 action）
├── README.md              # 本文档
├── backend/
│   └── router.py          # FastAPI router + 8 个 register_capability + 9 个 HTTP 端点（含 /health）
├── frontend/
│   └── index.vue          # 最简前端入口
├── runtime/
│   └── index.ts           # Runtime SDK（从 _template 复制）
└── sandbox/               # 独立开发环境（从 _template 复制）
```

## HTTP 端点（8 个，不含 /health）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/terminal-tools/health` | 健康检查（public） |
| POST | `/api/terminal-tools/exec` | 执行 shell 命令（editor+） |
| POST | `/api/terminal-tools/write-file` | 写文件到工作区（editor+） |
| POST | `/api/terminal-tools/read-file` | 读工作区文件（viewer+） |
| POST | `/api/terminal-tools/list-workspace` | 列工作区文件（viewer+） |
| POST | `/api/terminal-tools/publish` | 发布到框架文件系统（editor+） |
| POST | `/api/terminal-tools/import` | 导入框架文件到工作区（editor+） |
| POST | `/api/terminal-tools/run-python` | 运行 Python 代码（editor+） |
| POST | `/api/terminal-tools/chart` | 自动出图（editor+） |

## 验证

```bash
# 边界守卫
git diff --name-only  # 应仅在 modules/terminal-tools/

# 模块静态检查
backend/.venv/bin/ruff check modules/terminal-tools/backend/handlers modules/terminal-tools/backend/router.py

# 模块 sandbox 契约测试
python3.14 modules/terminal-tools/sandbox/test_module.py

# 技能注册确认
curl /api/modules/capabilities | grep terminal-tools

# 活系统能力验证（推荐经项目工具台 call_capability/probe）
# - write_file/read_file/list_workspace 正常路径
# - read_file 大文件截断
# - exec 危险命令与越界路径拦截
# - exec 超时与 stdout/stderr 截断
# - run_python 临时目录清理
# - chart 无图表上传时 success:false
```

## 边界验证清单

- [x] exec 在工作区跑命令正常
- [x] 越界路径（cat /Users/...、cd / 后操作）→ 被拒绝
- [x] 危险命令（sudo、rm -rf /）→ 被拦截
- [x] 超时命令（sleep 999）→ 被超时终止
- [x] stdout/stderr 先落工作区临时文件再按 1MB 截断返回
- [x] read_file/list_workspace 有返回上限并带 `truncated` 标记
- [x] API 响应不返回宿主机绝对路径
- [x] run_python 临时目录 finally 清理，input_files 不落工作区根目录
- [x] chart 无上传图表时不报假成功
- [x] publish 后文件出现在框架文件系统
- [x] import 后框架文件出现在工作区
- [x] owner 隔离: 用户只能操作自己的工作区

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `terminal-tools`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 8 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | PASS | Uses framework file APIs or capability bridge; file_id paths must preserve check_file_access. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/terminal-tools/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `terminal-tools:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep component_key empty so the launcher never opens a blank background window. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/terminal-tools/sandbox/test_module.py
cd modules/terminal-tools/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module terminal-tools --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
