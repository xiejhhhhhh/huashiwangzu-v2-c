# 框架开发文档

## 框架目标

框架负责桌面壳和平台加载能力，不承载具体业务模块。

目标目录归属：

```text
frontend/   桌面壳前端
backend/    桌面壳后端 / 平台服务层
modules/    被框架加载的业务模块
```

## 当前真实状态

- 当前 `frontend/` 已存在，是 Vue 3 + Vite 桌面壳。
- 当前前端入口是 `frontend/src/main.ts`。
- 当前登录、路由和入口页面在 `frontend/src/app-entry/`。
- 当前桌面窗口、任务栏、启动器、上下文菜单、应用注册表在 `frontend/src/desktop/`。
- 当前平台配置、指令、状态在 `frontend/src/platform/`。
- 当前共享 API、组件、composables、文件关联、上传能力在 `frontend/src/shared/`。
- 当前样式在 `frontend/src/styles/`。
- 当前桌面应用种子清单在 `backend/app/seed_data/apps.json`。
- 当前前端应用组件映射在 `frontend/src/desktop/app-registry/component-key-map.generated.ts`。
- 当前 `apps.json` / 数据库 `apps.component_key` 是应用入口组件 key 的来源；`.env` 只负责 `VITE_API_BASE`、`VITE_API_TARGET` 等运行环境配置，不负责应用入口 key。
- 当前 `modules/` 目录已存在，含 `ai-assistant/manifest.json` 和 `ai-assistant/sandbox/`。
- 当前 `modules/ai-assistant/manifest.json` 定义了 AI 助手模块占位入口。
- 当前构建管道包含 `scripts/scan-modules.js`，自动扫描 manifest 生成组件映射。
- 当前 `modules/ai-assistant/sandbox/` 是可独立运行的开发环境。
- 当前 `frontend/package.json` 构建脚本已修复为：`scan-modules.js` + `copy-pdf-worker.sh` + `vue-tsc -b` + `vite build`。
- 当前 `vite.config.ts` 已移除旧中文别名和自定义插件，新增 `@modules` 别名指向 `../modules`。
- 当前 `tsconfig.app.json` 路径已更新，移除旧 `后端/应用模块` 引用。
- 当前 `frontend/main.ts` 和 `v-permission.ts` 指令名改为英文。
- 当前所有前端 `@应用模块` 导入已被替换为 platform 原生调用或暂缺处理。
- 当前模块扫描链路已建立：`scripts/scan-modules.js` 扫描 `modules/*/manifest.json`，生成 `component-key-map.generated.ts`。
- 当前 `apps.json` 中所有非空 `component_key` 已改为英文路径：已有模块使用 `ai-assistant/index.vue`，其余待迁移应用使用 `apps/{app}/index.vue` 占位 key。`component-key-map.ts` 兼容层仍保留旧中文 DB 值到英文 key 的映射，避免未重新播种前中断。
- 当前应用组件 key 缺失时不再静默渲染空组件，窗口会显示 `ComponentRegistrationError` 并输出缺失的 app/key 信息。
- 当前前端构建脚本全部使用英文名称，构建命令链：`scan-modules.js` → `copy-pdf-worker.sh` → `vue-tsc -b` → `vite build`。
- 当前 `frontend/package.json` 中再无中文脚本名和旧 `脚本/` 路径引用。
- 当前 `window-types.ts` 接口已全部改为英文命名。
- 当前 `@应用模块` 导入全部移除。
- 当前 API 类型已修复（~30处中文属性名、语法损坏均已修正）。
- 当前外围 TypeScript 类型已修复：全量 `vue-tsc -b` 通过，0 错误。修复 20 处类型错误，涉及 7 个文件。
- 当前后端 router 注册已从 `main.py` 抽出到 `backend/app/routers/registry.py`，入口文件只调用 `register_routers(app)`。
- 当前后端 router registry 已支持模块 manifest 驱动挂载：模块 manifest 若声明 `backend.router`，框架会导入该文件并挂载其中名为 `router` 的 `APIRouter`；同时支持 `backend.enabled` 独立启停、路由 prefix 冲突/重叠检测，以及单模块加载失败时记录错误并跳过，不会拖垮整个平台。
- 当前 `shared/api/settings.ts` 已使用明确后端响应接口，不再用宽泛 `Record<string, unknown>` 解析主响应。
- 当前桌面根文件列表通过 API 层转换为英文 `items` 字段，消费侧不再读取中文 `列表` 字段。
- 当前后端 500 响应按 `APP_DEBUG` 控制错误详情：debug 模式返回异常详情，非 debug 模式返回固定错误文案。
- 当前桌面事件总线 payload 已改为英文字段，例如 `folderId`、`targetFolderId`、`targetAppKey`、`requestId`。
- 当前桌面状态前端内部结构已改为英文 `version/windows/appState`；读取历史中文 `版本/窗口/应用状态` 只允许发生在 API 边界迁移函数中。
- 当前窗口管理器导出已改为英文 `useWindowManager` / `windowManager`，核心方法为 `openWindow`、`closeWindow`、`toggleMinimized`、`toggleMaximized`、`activateWindow`、`restoreWindows`。
- 当前桌面任务栏组件 props / emits / class 已改为英文契约。
- 当前桌面壳前端框架基础设施已完成第二轮英文契约清理：composables、桌面加载、窗口框架、窗口交互、右键菜单、拖拽、框选、剪贴板、图标资产、启动器、托盘、右侧栏、通知面板等框架文件均使用英文导出名、props、emits、CSS class 和 DOM data 属性。
- 当前 `shared/api/desktop.ts` 文件 API 方法已改为英文命名，并明确转换后端响应包装。
- 当前通知 API 消费侧已按后端真实字段读取 `unread_count`、`list`、`is_read`，不再读取中文字段名。
- 当前 Element Plus 已改为 Vite 按需组件/样式导入，并拆分为 `element-core`、`element-overlay`、`element-components` 等 chunk；不再全量 `app.use(ElementPlus)` 和全量 `element-plus/dist/index.css`。
- 当前框架契约层核心文件已完成英文标识符清理：`action-registry.ts`、`desktop-app-handle-v2.ts`、`desktop-session-restore.ts`、`desktop-session-storage.ts`、`file-association-registry.ts`、`types-app-handle-v2.ts`、`v-permission.ts`。
- 当前框架样式契约已完成第三轮收尾：全局布局 class、共享状态组件 class、回收站 class、任务栏用户菜单 class、反馈提示 class、文件格式矩阵 class 已改为英文；CSS 自定义属性 `--边框色` 已改为 `--border-color`。
- 当前窗口类型使用英文值：`normal`、`panel`、`tool`、`fullscreen`、`background-service`。
- 当前后端框架 API 返回 message 已避免中文硬编码，`seed.py` 使用 logging 记录初始化结果，不再使用 `print()`。
- 当前后端健康检查已对数据库做实际连通性探测，`/api/health` 会返回 `database: ok/unreachable`。
- 当前 AI 网关对临时性 429/502/503/504 与连接超时错误使用指数退避重试，最终失败仍会明确返回错误，不会伪成功。
- 当前 `modules/_template/` 已创建，含标准化 sandbox 模板和 runtime 中间层，新模块复制即用。`scripts/scan-modules.js` 跳过 `_` 和 `.` 开头目录。
- 当前后端平台层已清理模块业务代码：`services/agent/`、`services/knowledge/`、`models/knowledge/`（16 个模型）、`schemas/knowledge.py` 及对应 18 个 router 已删除。模型网关保留为框架能力，迁至 `backend/app/gateway/`。`system.py` 中知识库端点已移除，`system_status_service` 和 `log_service` 中的模块引用已清理。
- 当前 `registry.py` 中 `PLATFORM_ROUTER_MODULES` 精简为 21 个纯框架 router，不再包含 AI 助手、知识库、图片视觉等模块业务路由。

## 已修复的 TypeScript 文件

| 文件 | 修复内容 |
|---|---|
| `shared/api/settings.ts` | 修复 `ApiResponse` 未定义、`参数.role`/`参数.username` 属性名不匹配、`项.role`/`项.role矩阵` 属性名不匹配 |
| `shared/components/system-status-panel.vue` | 模板中 `值.状态`→`值.status`、`值.消息`→`值.message` |
| `shared/components/file-format-matrix.vue` | `row.format`→`row.格式`、`attr.category`→`attr.分类`、`attr.description`→`attr.说明` |
| `shared/composables/use-settings-management.ts` | `用户.role`→`用户.角色`、`表单.value.username`→`表单.value.用户名`等 4 处 |
| `shared/composables/use-user-management.ts` | 同上 4 处 |
| `shared/upload/directory-upload.ts` | AxiosResponse 嵌套 `data` 路径修正 |
| `modules/ai-assistant/frontend/index.vue` | `res.success`→`res.data?.success`（3 处 AxiosResponse 类型适配） |

## 待办

- 数据库同步：当前 DB 可能仍存有旧中文 `component_key`，需在下次 `sync_apps_from_manifest` 运行后更新。同步前由 `component-key-map.ts` 兼容层翻译旧 key；同步后应以英文 key 为准。
- 开发辅助页 `desktop/design-system/module-layout-template.vue` 仍保留中文示例 class、布局名称和说明文字；它不属于运行时模块接入契约，后续可在设计系统整理时单独英文化。
- 框架契约层中文标识符已清理完毕；仍允许中文 UI 展示文案、toast、菜单 `label`、确认弹窗和业务显示值。若未来发现中文标识符出现在导出 API、props、emits、CSS class、DOM data 属性或类型字段中，应继续英文化。

## 当前框架能力

- 登录入口、桌面入口、全局布局。
- 窗口系统、任务栏、启动器、托盘、右侧栏。
- 应用注册、应用打开、窗口承载。
- 应用组件注册错误的显式展示。
- 共享请求器、响应转换、权限、主题、基础 UI 规范。
- 平台 API、数据库、队列、模型网关、文件存储、健康检查。
- 模块 manifest 动态挂载、模块加载错误可观测。

## 当前不属于框架的业务目标

- 知识库业务页面。
- AI 助手业务页面。
- 文件管理业务页面。
- 模块自己的状态、组件、业务流程。

## 目标模块扫描规则

框架只扫描顶层模块清单：

```text
modules/*/manifest.json
```

框架不递归扫描：

```text
modules/*/submodules/*
modules/*/sandbox/*
```

子模块由父模块管理。如果子模块需要出现在桌面启动器里，必须升级为顶层模块。

## 目标模块接入规则

模块接入框架时，必须通过模块 runtime：

```text
modules/{module}/runtime/
modules/{module}/runtime.config.json
```

页面、组件、composables 不直接拼接会随运行环境变化的路径。
## 已完成框架改进

### A. 后端改进

| 项 | 优先级 | 描述 | 状态 |
|----|--------|------|------|
| A1 | P0 | 统一模型配置源：registry.py 从 models.json 动态加载 | ✅ 已验证（6 条目） |
| A1 fix | P0 | 修复 registry.py 路径解析：缺少 `backend` 段 | ✅ 已修复 |
| A2 | P0 | 数据库连接池加固 | ✅ 已实施 |
| A3 | P1 | CORS 收紧：默认 `["*"]` 改本机 | ✅ 已实施 |
| A5 | P2 | 请求日志中间件 | ✅ 已创建 |
| A6 | P3 | 删除 health.py 端点重复 | ✅ 已删除 |

### B. 前端改进

| 项 | 优先级 | 描述 | 状态 |
|----|--------|------|------|
| B1 | P0 | 删除转中文()和中文属性名 | ✅ 已清理 |
| B2 | P1 | Vite 代码分割 | ✅ 已配置 |
| B3 | P1 | Vue 错误边界组件 | ✅ 已创建 |
| B4 | P2 | API_BASE_URL 环境变量 | ✅ 已发布 |
| B5 fix | P3 | DesktopAppItem snake_case 类型 | ✅ 已修复，构建通过 |

### 架构决策记录

**C1. 模型配置数据流**：models.json 是唯一事实源，registry.py 从 `watchdog_models` 段动态加载，不得硬编码。

**C2. API 字段命名**：后端 snake_case，前端在 `app-loader.ts` 统一转换为 `AppRegistryEntry` 的 camelCase。

**C3. 错误处理**：后端统一异常处理返回 `{success, data, error}`；前端 interceptors 捕获 401 重试+跳转。

**C4. Auth 令牌**：JWT HS256，24h 过期，嵌入 `session_version`，无 refresh_token。

**C5. 兜底分类**：Vue 组件渲染错误边界和 SPA 404 返回 `index.html` 是正常业务兜底；组件 key 缺失不允许静默返回空组件，必须显示注册错误或在构建/注册阶段失败。

**C6. Router 注册**：当前平台 router 通过 `backend/app/routers/registry.py` 集中注册，避免 `main.py` 堆叠 import/include；模块 router 由 manifest 的 `backend.router` 声明驱动，声明后必须真实导入并导出 `APIRouter`，失败即报错。

**C7. 模块后端动态挂载**：后端动态挂载必须由 manifest/runtime 驱动，不允许只靠手写 import 列表伪装动态化。当前已支持 `backend.router` 文件入口，并已补齐 `backend.enabled`、路由 prefix 冲突/重叠检测以及模块加载失败的可观测降级；后续再扩展权限声明和更细的运行时配置。

**C8. 应用入口 key**：`component_key` 是应用清单和数据库字段，决定前端加载哪个 Vue 入口组件；`.env` 是环境配置，不参与组件 key 解析。旧中文 `component_key` 只作为迁移兼容项存在，不能作为新模块写法。

**C9. 前端源码命名**：框架契约层必须使用英文命名；UI 展示文案、中文 toast、业务分类显示值可以保留中文。历史状态字段兼容只能出现在明确的边界转换函数中，不允许在业务消费侧继续读取中文字段。

**C10. Element Plus 构建优化**：Element Plus 不再全量注册，改用 `unplugin-vue-components` 和 `unplugin-auto-import` 按需导入；Vite manualChunks 将 Element Plus 拆为 core、overlay、components 等 chunk，避免单个超大 chunk。

**C11. Window type 值**：窗口类型必须使用英文枚举值。`normal` 表示普通窗口，`panel` 表示面板窗口，`tool` 表示工具窗口，`fullscreen` 表示全屏应用，`background-service` 表示后台服务。前端不得再用中文窗口类型字符串做判断。

**C12. 框架中文残留分类**：菜单 `label`、按钮文案、toast、确认框、表格列名、业务分类展示值属于正常 UI 中文展示；导出 API、props、emits、CSS class、DOM data 属性、TypeScript 类型字段、后端响应字段读取不允许使用中文绕过。兼容旧数据的中文 key 只能存在于明确命名的兼容映射或 API 边界转换中。

**C13. 测试覆盖策略**：框架测试与模块测试分层，互不冲突。框架测试（`backend/tests/`）覆盖框架自身——路由注册、API 契约、认证流、异常处理、健康检查、AI 网关重试——是模块接入的前提。模块测试在各自的 `sandbox/` 中运行，用 mini-shell 模拟桌面壳环境独立验证模块功能。框架测试不测试模块业务逻辑，模块 sandbox 不测试框架能力；两者互补，不存在重复或冲突。框架新增能力必须补对应框架测试；模块接入时模块作者在 sandbox 中写模块级测试。

**C14. 样式变量命名**：运行时框架 CSS class 和 CSS 自定义属性必须使用英文命名。主题色、文本色、圆角、阴影等旧中文变量后续触达时继续迁移为英文；新增样式不得引入中文 class 或中文 CSS 变量。

**C15. 部署场景与扩容决策**：本项目目标部署场景为单机局域网（20-50 人），后端和数据库在同一台机器上运行。基于此场景，以下扩容措施已评估为不需要：Redis 缓存层（PostgreSQL 连接池已满足 50 并发）、速率限制（内网信任环境）、JWT refresh_token（24h 过期足够工作日内使用）、水平扩展（单机单进程）。这些不是未完成事项，而是在目标场景下的主动决策；扩容需求变化时再重新评估。若部署场景扩大到公网或多机，优先考虑 Redis session store 和数据库读写分离。

### 验证

```bash
cd backend && .venv/bin/python -m pytest
# 41 passed（含认证流、API 契约、异常处理、健康检查、网关重试、模块注册冲突检测等核心框架链路覆盖，已删除模块业务测试）

cd frontend && npm run build
# 0 TS errors
# Element Plus 最大 JS chunk 约 475 kB，已拆分为 element-core、element-overlay、element-components 等 chunk，不再触发 500 kB chunk 警告
```

当前关键扫描：

```bash
rg -n "\bas any\b|@ts-ignore|@ts-expect-error|:\s*any\b" frontend/src backend/app
rg -n "raise HTTPException|return ApiResponse\(success=False|ApiResponse\(success=False" backend/app
rg -n "default:\s*null|Promise\.resolve\(\{ default: null \}\)" frontend/src
rg -n "use窗口管理器|窗口管理器|use桌面事件总线|文件夹id|目标文件夹id|获取文件列表请求|上传文件请求" frontend/src/desktop frontend/src/shared
rg -n "component_key\": \"应用/|window_type\": \"background\"|保存成功|导出成功|print\(" backend/app frontend/src
rg -n -- "--边框色|var\(--边框色" frontend/src
```

上述扫描不应出现框架绕过项；Python 内置函数 `any(...)` 不属于类型绕过。若中文扫描命中 `label`、toast、确认框、表格列名、业务数据字段或开发辅助页示例，按 C12 / C14 归类，不视为类型绕过或偷懒兜底。
