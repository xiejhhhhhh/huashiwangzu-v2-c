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
| 业务模块 | 当前无已接入模块；AI 助手/知识库待从 V1 或新设计重建 |
| 前端构建 | `vue-tsc -b` 0 错误，Element Plus 最大 chunk ~475 kB |
| 后端测试 | pytest 72 通过（G9–G12 修复后）|

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

禁止模块 `import frontend/src/*`、`import backend/app/services/*`、直接读写框架数据库表。

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
