# 框架开发文档

## 框架目标

框架负责桌面壳和平台加载能力，不承载具体业务模块。

```text
frontend/   桌面壳前端（Vue 3 + Vite）
backend/    平台服务层（FastAPI + SQLAlchemy）
modules/    被框架加载的业务模块（物理隔离、sandbox 独立开发）
```

## 当前状态速览

| 分类 | 状态 |
|------|------|
| 前端入口 | `frontend/src/main.ts`，Vue 3 + Vite + Pinia + Element Plus（按需导入，chunk 拆分） |
| 桌面壳 | 窗口系统、任务栏、启动器、托盘、右键菜单、应用注册表、文件关联调度器 |
| 后端入口 | `backend/app/main.py`，22 个平台 router，统一响应 `{success, data, error}` |
| 数据库 | 21 张 `framework_*` 表，干净基线迁移 `v2_clean_framework_baseline` |
| 模型网关 | `backend/app/gateway/`，DeepSeek/OpenCode/OpenAI 兼容，指数退避重试 |
| 模块模板 | `modules/_template/`，含 sandbox 开发环境 + runtime SDK 壳 |
| 业务模块 | 已接入 12 个：agent（AI助手，含三层提示词/桌面感知/终端工具）、codemap（代码地图）、desktop-tools、terminal-tools、excel-engine、6 个格式解析（pdf/docx/pptx/xlsx/text/image-vision）、hello-world 样板（另含模板 1 个 `_template`）。知识库待迁 |
| 前端构建 | `vue-tsc -b` 0 错误，Element Plus 最大 chunk ~475 kB |
| 后端测试 | pytest 72 通过（G9–G12 修复后）|

## 本地运行入口与端口(分清主框架 vs 模块沙盒)

**同事/华哥日常测试 = 主框架。** 模块沙盒只给开发某个模块时单独调试用,两者是不同的进程和端口,别混。

| 跑什么 | 谁 | 地址/端口 | 怎么起 | 常驻? |
|--------|----|-----------|--------|-------|
| **主框架·前端** | 桌面壳(加载所有模块,框架统一登录发 token) | `http://127.0.0.1:5173` | `cd frontend && npm run dev` | 否(开发服务器,关终端就没) |
| **主框架·后端** | 平台服务层 FastAPI | `127.0.0.1:33000` | `scripts/start_backend.sh`(watchdog 守护) | ✅ 是(崩了自动拉起) |
| 模块沙盒·agent | Agent 模块单独调试壳(**自己的登录表单**,非框架登录态) | 前端 `127.0.0.1:5180` / 后端 `38010` | `cd modules/agent/sandbox && bash run.sh` | 否 |

**关键区别**：
- 主框架前端访问 **必须带端口 5173**——直接开 `127.0.0.1`(=80 端口)会 `ERR_CONNECTION_REFUSED`,因为 80 上没服务。
- 主框架里 Agent 走 `modules/agent/frontend/index.vue`，登录/token 由**框架统一接管**（runtime SDK `authHeaders()`），模块沙盒的登录壳 `sandbox/src/App.vue` **不上场**。
- 模块沙盒(5180)是**独立世界**，没有框架登录态，要在沙盒里单独登录拿 token——开发自测用，跟生产无关。
- 端口约定：主框架前端固定 5173，**模块沙盒一律避开 5173**（agent 沙盒用 5180），防止跟主框架抢端口。新模块沙盒照此避开。

> 鉴权链路自测(命令行)：`POST /api/login {username,password}` 拿 `access_token` → 带 `Authorization: Bearer <token>` 调模块接口。无 token = 401，有效 token 不再 401(字段不对会是 422，与鉴权无关)。

## 框架能力清单

### 桌面壳

| 能力 | 位置 |
|------|------|
| 窗口管理（打开/关闭/最小化/最大化/激活） | `frontend/src/desktop/window-manager/` |
| 任务栏、启动器、托盘、右侧栏 | `frontend/src/desktop/` |
| 应用注册表 + 组件映射 | `frontend/src/desktop/app-registry/` |
| 桌面文件图标 + 右键菜单 + 拖拽上传 | `frontend/src/desktop/shell/` |
| 模块 manifest 扫描 + 动态挂载 | `frontend/scripts/scan-modules.js` |

### 文件系统底座

| 能力 | 后端 API | 前端调度 |
|------|----------|----------|
| 文件 CRUD | `GET/POST /api/files/*` | `shared/api/desktop.ts` |
| 上传/下载/预览 | `POST /api/files/upload` `GET /api/files/download/{id}` `GET /api/files/preview/{id}` | — |
| 移动/复制/重命名 | `POST /api/files/{move,copy,rename}` | — |
| 搜索 | `GET /api/files/search?keyword=&extension=` | — |
| 回收站 | `GET/POST /api/recycle/*` | `shared/components/recycle-bin-view.vue` |
| 内容去重 | `md5_hash` + `ref_count` + 内容寻址存储路径 | — |
| 文件分享 | `POST /api/files/share` `GET share/{received,sent}` `DELETE share/{id}` `GET share/check/{file_id}` | — |
| 批量操作 | `POST /api/files/batch-delete` `POST /api/files/batch-move` | — |
| 路径面包屑 | `GET /api/files/path/{item_type}/{item_id}` | — |
| 审计日志 | 12 种操作写入 `framework_system_logs` | — |

**关键规则**：

- 所有查询按 `owner_id` 隔离，跨用户操作拒绝（403）
- 重名返回 409；复制用 ` copy` / ` copy 2` 递增
- 回收站恢复含祖先路径递归恢复 + 冲突检测；原目录不存在时降级到根目录
- 文件打开调度：`editable_formats` 优先 → `sort_order` 排序 → 无匹配明确报错（不 fallback）
- `["*"]` 仅 `desktop` 应用允许，其他应用声明 `["*"]` 被调度器忽略

### Office 文档底座

| 表 | 用途 |
|----|------|
| `framework_file_json_packages` | JSON 包 |
| `framework_file_json_versions` | 版本记录 |
| `framework_file_json_patches` | 补丁记录 |
| `framework_file_json_tasks` | 文档任务 |

### 模块公开接口

模块通过三条路径与框架交互：

| 路径 | 说明 |
|------|------|
| HTTP API | `/api/*`，统一响应 `{success, data, error}` |
| Runtime SDK | `modules/{module}/runtime/index.ts` 的 `platform` 对象 |
| manifest 声明 | `manifest.json`：组件入口、`supported_formats`、权限、后端 router |

Runtime SDK 的 `platform` 对象含 9 个 namespace：`auth`、`files`、`office`、`gateway`、`tasks`、`notifications`、`logs`、`settings`、`modules`（跨模块调用，含 `call`/`capabilities`）。

### 模块可用框架公开能力清单

模块可以调用框架公开能力，但不能把框架内部实现当业务依赖。当前事实源如下，codemap 边界检查以此清单判定：

| 类型 | 允许模块使用 | 规则 |
|------|--------------|------|
| 后端数据库会话 | `app.database.get_db`、`app.database.AsyncSessionLocal` | 只作为连接和事务入口；模块只能读写自身 `{key}_*` 表，不能直接读写 `framework_*` 或其他模块表 |
| 鉴权与当前用户 | `app.middleware.auth.require_permission`、`app.models.user.User` | router 依赖注入用；业务查询不得绕过 owner/user 隔离 |
| 统一响应与异常 | `app.schemas.common.ApiResponse`、`app.core.exceptions.AppException`/`NotFound`/`ValidationError`/`ConflictError`/`PermissionDenied` | API 必须保持 `{success,data,error}`；业务错误抛异常，不返回假成功 |
| 模块能力注册/调用 | `app.services.module_registry.register_capability`、`call_capability`、`list_capabilities` | 跨模块调用唯一后端通路；禁止 import 其他模块代码 |
| 任务队列 | `app.services.task_worker.register_task_handler`、`app.models.system.SystemTaskQueue` | 模块注册 handler 或投递框架任务；任务 payload 只存逻辑 ID |
| 模型网关 | `app.gateway.router.gateway_router` | 作为统一模型入口；模块不得绕过网关散落 provider/key |
| 框架文件/应用桥接 | `app.models.file.File/Folder`、`app.models.app.App`、`app.services.file_service`（推荐入口：`check_file_access(db, file_id, user_id)`）、`file_upload_service`、`file_preview_service`、`app.services.app_service.can_user_access_app`、`app.config.get_settings` | 仅限桥接型模块或文件解析/发布场景；读盘前必须先经 `check_file_access` 校验 owner/share；禁止直接 `db.get(File, file_id)` 后读文件内容；其他文件操作必须经框架服务函数保持 owner 隔离、去重、审计等底座规则 |
| SQLAlchemy 基类 | `app.models.base.Base`、`TimestampMixin` | 模块 ORM 可复用基类；模块表仍不得加到框架迁移或加跨表外键 |
| 前端 runtime SDK | `modules/{module}/runtime/index.ts` 注入的 `platform` 对象 | 模块前端优先通过 runtime 调 `auth/files/office/gateway/tasks/notifications/logs/settings/modules` |
| 前端共享工具 | `frontend/src/shared/` | 仅可使用明确共享的 API/组件；不得 import `frontend/src/desktop/`、`frontend/src/router/`、`frontend/src/stores/` 等壳内部实现 |

未列入本表的 `backend/app/services/*`、`backend/app/models/*`、`backend/app/routers/*`、`backend/app/middleware/*`、`backend/app/core/*`、`backend/app/gateway/*` 和 `frontend/src/*` 均按框架内部实现处理。确有多个模块都需要的新能力，先作为独立框架任务把契约写进本清单，再让模块使用。

禁止模块 `import frontend/src/*`（除 `frontend/src/shared/`）、导入未列入本清单的 `backend/app/*` 内部实现、直接读写框架数据库表或其他模块表。

### 扩展边界

| 类型 | 内容 |
|------|------|
| 已实现 | 批量操作、路径面包屑、错误码（400/403/404/409/413/500）、12 种文件操作审计日志 |
| 预留 | 文件元数据（`framework_file_metadata`）、标签（`framework_file_tags`）、全文索引、缩略图、磁盘配额 |
| 后置 | 外链分享、团队空间、文件夹分享、虚拟"与我共享"目录、文件版本化 |

## 架构决策

| # | 决策 |
|---|------|
| C1 | 模型配置唯一事实源 `models.json`，registry.py 动态加载 |
| C2 | API 字段：后端 snake_case，前端 app-loader 转为 camelCase |
| C3 | 统一异常处理 `{success, data, error}`；前端 401 拦截重试+跳转 |
| C4 | Auth：JWT HS256，24h，嵌入式 `session_version`，无 refresh_token |
| C5 | 组件 key 缺失 → 显示注册错误，禁止静默空窗口 |
| C6 | Router 注册集中在 `registry.py`；模块由 manifest 驱动挂载 |
| C7 | 模块后端必须由 manifest/runtime 驱动，禁止手写 import 列表伪装动态化 |
| C8 | `component_key` 是数据和 DB 字段；`.env` 不参与组件 key 解析 |
| C9 | 框架与模块物理隔离：开发在 sandbox，集成通过契约（manifest + SDK + API） |
| C10 | 框架契约层英文命名；UI 展示文案可中文 |
| C11 | Element Plus 按需导入，Vite chunk 拆分 |
| C12 | 窗口类型英文枚举：normal / panel / tool / fullscreen / background-service |
| C13 | 样式 class 和 CSS 变量英文命名 |
| C14 | 部署：单机局域网 20-50 人，不需要 Redis/限流/refresh_token/水平扩展 |
| C15 | 文件 owner 隔离：所有查询按 `owner_id` 过滤；create/move/copy 校验目标目录 owner |
| C16 | 内容去重：`md5_hash` + 内容寻址，相同内容共享一份物理文件（复制也复用，不另存）；删除统计同 md5 未删除记录数，归零才删盘（`ref_count` 为冗余字段，不参与删除判断）；分享：`framework_file_shares` + owner/shared 双重检查 |
| C17 | 打开调度：`editable_formats` 优先 + `sort_order` + `["*"]` 仅 desktop |
| C18 | 表命名：`{owner}_{domain}_{sub_domain}`，框架 `framework_*`，模块用自身 key |
| C19 | 模块公开接口：HTTP API + runtime SDK（9 namespace）+ manifest |
| C20 | 框架 = 公共能力层（商场模型）：框架只提供横向公共能力，数量固定稳定，**不随模块数量膨胀**；模块的业务表与业务接口全在模块自己里，加模块不改框架。这是兼容性的根（类比 Windows：系统接口几十年不变，软件自带业务） |
| C21 | 跨模块调用必须 100% 经框架统一通路，禁止互相 import / 直接读对方表。前端：runtime SDK 已暴露 `platform.modules.call/capabilities`（底层经 `desktop-app-handle-v2` 的 `sendCommand`/`requestData` + `registerActionHandler` + 权限/审计/超时）；后端：模块能力注册表 `module_registry.py` + `/api/modules/call` + `/api/modules/capabilities`，运行时以 `register_capability` 注册为准，manifest `public_actions` 当前作为声明元数据同步 |
| C22 | **Agent 终端工具安全边界（已决策，新会话勿再提"要不要 Docker 强隔离"——这是权衡后的明确选择）**：① **本地执行，不用 Docker**（Docker 重复装环境、占资源、拉起慢，不划算）；② **行为边界**=命令子进程 cwd 锁死用户工作区 `data/workspaces/{user_id}/` + 文件路径约束在工作区内（越界绝对路径/`../`/`~` 拒绝）+ 危险命令拦截（`sudo`/`rm -rf /`/访问工作区外）+ 执行超时 + 输出大小上限；③ **联网允许**（局域网内部场景，不限死）；④ **两套世界分离**=桌面/文件感知走 `desktop-tools`（框架文件系统，**非宿主机桌面**）、命令执行走 `terminal-tools`（工作区，**非宿主机其他路径**），CLI 绝不指向宿主机真实桌面/文件；⑤ **产物**=工作区是草稿（不上桌面），成果由 Agent 显式 `publish` 进框架文件系统才上桌面，未交付的临时文件按会话结束/超时/超大小自动清。隔离强度 = 应用层约束 + 局域网信任同事（够用），**非 Docker 级强隔离系明确取舍，不是遗漏** |

## 验证命令

```bash
# 后端
cd backend && .venv/bin/python -m pytest

# 前端
cd frontend && npm run build

# 关键扫描
rg -n "ChatSession|ChatMessage" backend/app backend/migrations          # 期望 0
rg -n '__tablename__ = "(users|apps|files|...)"' backend/app/models    # 期望 0
rg -n "owner_id" backend/app/services/file_service.py                  # 期望全部查询有
rg -n "md5_hash|ref_count|deduplicated" backend/app                    # 期望有输出
rg -n "supported_formats|editable_formats" frontend/src                # 期望有调度逻辑
rg -n "export const platform" modules/_template/runtime/index.ts       # 期望有输出
```
