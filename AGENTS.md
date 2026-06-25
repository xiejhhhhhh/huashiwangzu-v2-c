# Huashiwangzu V2 Agent Rules

## First Entry

Read this project entry first:

```text
开发文档/README.md
```

Then read the matching documentation by task type:

```text
开发文档/01_框架开发文档/README.md
开发文档/02_底层开发文档/README.md
开发文档/03_模块开发文档/README.md
开发文档/03_模块开发文档/{number_module_name}/README.md
```

## Project Status

- V2 is a clean architecture rebuild, not a patch layer over the old Laravel/PHP tree.
- V1 reference: `../华世王镞_v1/`. It is read-only and must not be modified.
- If a missing capability is needed, inspect V1 or historical versions, then rebuild it under the V2 architecture.
- Target structure: `frontend/ + modules/ + backend/`.

## Architecture Boundary

```text
frontend/   Desktop shell frontend
modules/    Business modules and desktop apps
backend/    Desktop shell backend / platform service layer
```

- Framework capabilities belong in `frontend/` or `backend/`.
- Business capabilities belong in `modules/`.
- Every module must pass its own `sandbox/` validation before integration into the main shell.

## Hard Rules

1. Outside the `开发文档/` documentation tree, every directory name and file name must be English.
2. `开发文档/` is the user-facing documentation tree; Chinese directory names, file names, and prose are allowed there.
3. Markdown documents have no line or word limit.
4. Normal source files should stay within 600 lines; strongly coherent flows may go up to 1000 lines.
5. Python code must use English names, type annotations, and Router -> Schema -> Service -> Model layering.
6. API responses must use the unified JSON shape: `{ "success": true, "data": ..., "error": ... }`.
7. Test data must be cleaned up after use. Whoever creates it is responsible for removing it.
8. Code comments may use Chinese. Markdown prose outside `开发文档/` must use English.
9. Paths, file names, module names, variable names, and configuration names must be English outside `开发文档/`.
10. Do not restore `后端/`, `脚本/`, `部署/`, `backend/_废弃/`, or `backend/脚本/`.
11. Do not commit empty features, temporary comments, or fake-success logic.
12. When a temporary task document is complete, merge the useful result back into the relevant `README.md`, then delete the temporary document.
13. After code changes, run the relevant tests. For backend changes, default to `cd backend && pytest`.
17. **跨模块调用必须 100% 经框架统一通路。** 模块之间（如 Agent 调知识库）禁止互相 `import` 代码、禁止直接读写对方的数据库表。只能通过框架的跨模块通路（前端 runtime SDK `platform.modules.call/capabilities`；后端 `/api/modules/call` + 能力注册表）。后端运行时以 `register_capability` 注册为准，未注册能力不可被其他模块调用；manifest 的 `public_actions` 当前作为对外能力声明元数据。详见 `开发文档/03_模块开发文档/README.md` → 模块数据与交互契约。
18. **框架接口不随模块膨胀。** 模块的业务表（`{key}_*` 前缀）和业务接口（`modules/{key}/backend/router.py`）全在模块自己里，加模块不改框架。只有"所有模块都需要的新公共能力"才往框架加接口，且要保持长期稳定（契约）。
19. **模块开发任务禁止修改框架（调用可以、修改不行）。** 做某模块任务时，所有改动只许落在 `modules/{该模块}/` 内。可**调用**框架公开能力（数据库连接、统一响应、模型网关、runtime SDK、跨模块注册表），但禁止**修改** `backend/app/`、`frontend/src/` 或其他模块。模块需要框架新增公共能力时，必须作为独立「框架任务」单独提出。**验收硬守卫**：每个模块任务必跑 `git diff --name-only`，凡改动落在 `modules/{当前模块}/` 之外，直接判不通过。
20. **后端模块"独立开发"= 独立运行 + 只碰自己的表 + 不碰其他模块，不是"代码零依赖框架"。** 后端模块用框架的数据库连接、统一响应、模型网关是正常且必须的（公共能力），**直接调真的即可**，不得另造一套。数据与外部依赖：全新项目可直接连生产库、调真网关（省事，边界由"只碰 `{key}_*` 表"限制死）；如需隔离测试，也可用独立库/ mock，但不强制。
21. **Agent 终端/CLI 工具的安全边界已定，勿再质疑"要不要 Docker 强隔离"（这是权衡后的明确取舍，不是遗漏）。** 终端工具**本地执行（不用 Docker）**；行为边界：命令 cwd 锁死用户工作区 `data/workspaces/{user_id}/`、文件路径约束工作区内、危险命令（`sudo`/`rm -rf /`/越界）拦截、执行超时 + 输出上限、联网允许（局域网）。**两套世界分离**：桌面/文件感知走 `desktop-tools`（框架文件系统，**非宿主机桌面**）、命令执行走 `terminal-tools`（工作区，**非宿主机其他路径**），CLI 绝不指向宿主机真实桌面/文件。产物：工作区是草稿，成果显式 `publish` 才上桌面，临时文件自动清。隔离强度 = 应用层约束 + 局域网信任同事（够用）。详见 `开发文档/01_框架开发文档/README.md` C22。
22. **多 worker 下共享状态必须持久化，纯内存不跨 worker。** 后端跑 `--workers 3`，进程内内存（锁、缓存、计数器、限流、去重表）**各 worker 各一份、互不可见**。任何需要跨请求/跨 worker 一致的状态，必须落地到文件（原子写：temp+rename）或数据库；后台任务要防多 worker 重复消费。codemap 文件锁存 `locks.json` 即此故。
23. **模块读框架文件必须走 `check_file_access`，禁止裸 `db.get(File)` 后直接读盘。** 任何按 `file_id` 取文件内容的端点（parser/解析/预览/发布），都要先用框架 `check_file_access(db, file_id, user_id)` 校验 owner/share，再读盘——否则任何登录用户凭 id 越权读他人文件（曾是 P0）。owner 从 caller（`user:{id}`）解析，不得写死。
24. **改/查代码前先用 codemap 查影响面，别埋头逐文件翻——省 token、更准。** 后端起着时：`PORT=$(cat backend/logs/.backend.port 2>/dev/null||echo 33000)`；`POST /api/codemap/impact {"path":"<要改的文件>"}` 拿"波及哪些文件/模块/能力"，`POST /api/codemap/get-file {"path":...}` 拿直接依赖。**看返回的 `confidence`(0-100，解析覆盖率) 和 `stale`(索引是否最新) 判断可信度**：confidence 低或 `stale:true` 时以实读为准。返回的 `empirical_accuracy` 是实战命中率（基于历史反馈），优先参考。**命中关联文件后，改之前必实读该文件做验证，不盲信 codemap 结论**。**实读验证后若发现 codemap 给的关联/影响面不准，调 `report_inaccuracy` 反馈一条（path + codemap说的 + 实际 + 原因），让信任分和维修记录积累起来。** codemap 不可用（health 非 200）才回退逐文件查，别卡住。这是默认工作流，能用就用。
25. **首选 codegraph 查代码/查影响面，再回退 codemap/grep——省 token。** 本仓已 `codegraph init`（`.codegraph/` 本地索引，文件改动自动同步）。改代码或答"X 怎么工作/在哪/谁调用/改了影响啥"之前，**先调 codegraph**：`codegraph_explore`（PRIMARY，传符号名或自然语言问题，一次返回相关符号的逐行源码+调用关系+影响面+有无测试覆盖，等价已 Read，别再开这些文件）；`codegraph_node`（单符号/读整文件带依赖者）；`codegraph_callers`/`codegraph_impact`（谁调用/改动波及面）。**改前看 blast radius 再下手**。MCP 工具不可用时用 CLI：`codegraph explore "<符号/问题>"`、`codegraph node <符号或文件>`。codegraph 与 codemap 重叠时优先 codegraph（全局、自动同步、跨 agent）；两者都不可用才 grep/逐文件读。
26. **桌面壳禁用全局快捷键（键盘热键）。** 本系统是跑在真实电脑浏览器里的 Web 应用，**绝不抢占键盘快捷键**——不做 Alt+Tab 切窗、Win+方向键分屏、Ctrl+Shift+P 命令面板这类全局热键绑定，因为会和用户的操作系统/浏览器/其它软件快捷键冲突，体验很恶心。所有交互入口走**鼠标可点的可见控件**（任务栏、启动器、右键菜单、按钮、磁吸拖拽）。命令/功能可以做统一注册中心供菜单和可见入口调用，但**不绑全局快捷键触发**。调研或方案里凡涉及"快捷键/热键/keybinding"的交互，一律不采纳。（仅限输入框内的常规编辑键如 Enter 提交、Esc 关弹窗这类局部、不抢全局的除外。）

## TypeScript Rules

14. **禁止使用 `any` 类型绕过类型检查。** 未知 API 响应先定义正确接口类型，而非写 `as any` 或 `@ts-ignore`。类型错误就是真 bug，必须修复而非压制。
15. **前端代码访问 API 响应的字段名必须与后端实际返回一致。** 后端返回 `entry_component_key` 则前端也读 `entry_component_key`，不依赖 `转中文()` 转换后的中文名或未定义的 camelCase 别名。若需要映射，在消费侧显式转换，类型定义与运行时必须对齐。
16. **`转中文()` 是 UI 展示层的纯字符串映射工具（下拉文本、toast、按钮文案），不可用于改变字段名或跳过类型检查。** 需访问的数据字段，代码直接读英文名。

## 开工铁律(项目工具台 MCP)

1. **每个开发 agent 开工先连"项目工具台"MCP**: 调 `brief()` 了解全貌→`code_explore`/`codegraph` 查代码与影响面→`routes`/`capabilities`/`db_schema` 查准端点/能力/表(别猜)→改完 `lint` 静态查错→`probe`/`call_capability` 直接打活系统验(别写测试脚本搭场景)→单测用 `run_test`→收工**必须用 `memory_write(agent="<自己>")`** 落一条"我是谁/干了啥/commit"(禁止手写JSON/文件到别处)。记忆唯一位置 = `开发文档/项目记忆/`(markdown)。
2. **跨模块归因**: 每个 agent 任务完成必 `memory_write(agent="<agent名>")` 留一条, 注明 agent、干了啥、关联 commit。重复主题用更新不新建。
3. **查代码优先 codegraph**: `code_explore`/`code_node`/`code_impact` 或直接 `codegraph` CLI。
4. **读网页用 `web_read`**(不截图)。
5. **测试直接用 `probe` / `call_capability` 打活系统** + `tail_log` 看错, 别写测试脚本搭场景。
6. **★产物验证铁律(报"通过"前必做)**: 凡涉及**后台/异步/hook/事件/落库**的功能(如 review fork、stuck 检测、知识库入库、画像演进),做完真实触发后**必须两查**:① `log_errors(module)` 扫有没有被 try/except 吞掉的异常(命中=功能其实没跑通,**禁止报通过**);② `sql`/`db_schema` 查**产物表真有行**(不是只看"任务建了/表存在")。**"任务建了 ≠ 产物出来了"**。栽过两次:stuck 漏 owner_id 插入崩、review fork 错参全程不产 proposal——都是异常被吞成 WARNING、产物表 0 行,只查"表在"就漏了。

## 测试铁律

以下测试规则为唯一定义，其他文档引用此处，不重复定义：

1. **活栈是常驻夹具，测试只访问不重建** — 后端的 33000、前端的 5173 是常驻服务，测试只通过 HTTP 访问，不启动/停止服务。只有改代码需重置时才重启。
2. **登录一次(storageState)全程复用** — Playwright 测试以 `globalSetup` 登录一次，存储 localStorage 到 `.auth/{role}.json`，各 test 通过 `test.use({storageState})` 复用，禁止每测重登。
3. **条件等待，禁止硬等** — 使用 `waitForSelector`/`waitForResponse`/`expect(locator).toBeVisible()` 等条件等待，禁止 `sleep`/`waitForTimeout`（极少数需稳定间隔处保留但加注释说明）。
4. **优先黑箱打活系统** — 用 `probe`/`call_capability` 直接验证后端行为，少写测试脚本搭场景。UI 测试才用 Playwright。

MCP server 入口: `python3.14 dev_toolkit/server.py` (stdio), 注册在 `.mcp.json`。

## Scan Boundaries

Allowed:

```text
backend/app
backend/tests
frontend/src
modules
开发文档
```

Do not scan:

```text
frontend/node_modules
backend/.venv
backend/venv
.git
__pycache__
*.pyc
```
