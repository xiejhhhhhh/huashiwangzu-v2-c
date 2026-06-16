# 底层开发文档

## 底层目标

底层指 `backend/` 平台服务层，以及脚本、部署、数据库、模型、队列等基础能力。它提供平台能力，不承载模块业务流程。

## backend 定义

`backend/` 是平台服务层，不是业务后端大杂烩。

## 当前真实状态

- 当前 `backend/` 已存在，是 Python FastAPI 后端。
- 当前后端入口是 `backend/app/main.py`。
- 当前已注册多个 router 文件，覆盖认证、桌面、文件、回收站、用户、角色、系统、日志、仪表盘、设置、备份、任务、Office、通知、反馈、应用管理、AI 助手、健康检查、图片视觉、知识库等。
- 当前数据库初始化和释放在 `backend/app/database.py`，应用生命周期在 `backend/app/main.py`。
- 当前 ORM model 在 `backend/app/models/`。
- 当前 schema 在 `backend/app/schemas/`。
- 当前 router 在 `backend/app/routers/`。
- 当前 service 在 `backend/app/services/`。
- 当前 AI 助手服务仍在 `backend/app/services/agent/`。
- 当前知识库服务仍在 `backend/app/services/knowledge/`。
- 当前模型看门狗在 `backend/app/services/model_watchdog/`。
- 当前默认 AI 助手模型为 `deepseek-v4-flash`，通过 `backend/app/services/agent/gateway/router.py` 路由。
- 当前模型网关在 `backend/app/services/agent/gateway/`，包含 `opencode`、`llama`、`local` provider。
- 当前旧 `/api/chat/.../stream` 兼容入口仍在 `backend/app/routers/system.py`。

## 当前底层职责

- FastAPI 应用入口和路由注册。
- 数据库连接、事务、迁移、ORM 模型。
- 权限、角色、鉴权中间件。
- 队列、定时任务、worker。
- 模型看门狗、llm 网关、embedding / rerank。
- 文件存储、上传下载、预览资源。
- 系统日志、健康检查、备份恢复。

业务模块可以调用这些能力，但业务本身归 `modules/`。

## 脚本和部署

正式脚本使用英文目录：

```text
scripts/
backend/scripts/
frontend/scripts/
modules/{module}/sandbox/
deploy/
ops/
```

不再使用：

```text
脚本/
部署/
backend/脚本/
```

## 测试和数据清理

- 测试可以创建数据，但必须清理。
- 上传样例、临时文件、测试日志、缓存结果不得长期保留。
- 数据库测试记录必须回滚或删除。
- 测试结果目录不作为事实源。

## 当前任务完成状态

- ✅ 01_明确backend平台边界.md — 概念文档，无代码变更
- ✅ 02_统一AI模型网关和旧兼容入口.md — AI 助手前端已构建并正常工作（登录、建会话、收发消息），默认模型 deepseek-v4-flash，旧 /api/chat/* 兼容入口存在并通过 nginx 正常响应（32 个会话），复用同一 gateway_router
- ✅ 03_清理旧目录和缓存残留.md — 旧中文目录（后端/ 脚本/ 等）已移除，backend/scripts/ 下四个子目录用途明确（maintenance/models/worker/），无残留测试数据
- ✅ 04_后端硬编码与模型配置化.md — P0 全部完成：models.json 已落盘（3 providers + 4 model types + 4 LLM profiles），看门狗 3 个 provider 全部在线，模型配置 JSON 驱动，知识库 catalog API 正常返回，embedding 服务路由已接入

## 实测结论

| 测试项 | 结果 |
|--------|------|
| 登录流程 | ✅ 浏览器实测通过，成功跳转 /desktop |
| AI 助手打开 / 建会话 / 发消息 | ✅ 浏览器实测通过，SSE 流式回复正常 |
| 旧 /api/chat/ 兼容入口 | ✅ 通过 nginx 正常响应，32 个历史会话可查 |
| 文件系统 API | ✅ /api/files/tree 返回正常 |
| 知识库 catalog | ✅ /api/knowledge/catalogs 返回正常 |
| 模型配置（models.json） | ✅ 4 种模型类型 + 3 个 provider + 4 个 LLM profile |
| AI 网关 | ✅ 3 个 provider 全部在线 |
| 严格模式 TypeScript | ✅ `转中文()` 已移除，vue-tsc 零错误 |
| 旧中文目录 | ✅ 已移除 |
| `as any` / `@ts-ignore` 绕过 | 0 处 |

## 二次实测验证（2026-06-16）

| 测试项 | 结果 | 说明 |
|--------|------|------|
| 登录 /api/login | ✅ 通过 | admin/admin123，返回 JWT token + user 对象 |
| AI 助手创建会话 | ✅ 通过 | POST /api/agent/sessions 返回 id=45, model=deepseek-v4-flash |
| AI 助手会话列表 | ✅ 通过 | 45 个会话，全为 deepseek-v4-flash 模型 |
| 旧 /api/chat/sessions | ✅ 通过 | 33 个会话，model=deepseek-v4-flash，复用 gateway_router |
| 模型网关状态 | ✅ 通过 | 3 providers (opencode/llama/local) 全部 online |
| 仪表盘 /api/dashboard/stats | ✅ 通过 | 返回文件数 331、用户数 4 等统计数据 |
| 通知 /api/notifications/unread-count | ✅ 通过 | 返回未读数 0 |
| 文件系统 /api/files/tree | ✅ 通过 | 返回文件目录树 |
| 知识库 /api/knowledge/catalogs | ✅ 通过 | 返回编目列表 |
| 当前用户 /api/current-user | ✅ 通过 | 返回 id=1, username=admin, role=admin |
| 健康检查 /api/health | ✅ 通过 | status=ok, version=2.0.0 |

### TypeScript 严格模式验证

| 检查项 | 结果 |
|--------|------|
| vue-tsc --noEmit | ✅ 零错误通过 |
| vite build | ✅ 成功构建 (292ms) |
| `转中文()` 被拦截器调用 | ✅ 已移除 — 拦截器直接透传原始 JSON |
| `转中文()` 死代码隔离 | ✅ 仅在 response-transform.ts 中定义，无外部 import |
| as any 绕过 | 0 处 |
| @ts-ignore / @ts-expect-error | 0 处 |

### 框架问题修复

| 问题 | 类型 | 操作 | 状态 |
|------|------|------|------|
| `部署/` 中文目录残留 | 框架 | 已删除（含 nginx/logs 空子目录） | ✅ 已修复 |
| `转中文()` 在响应层自动调用 | 框架 | 已从拦截器移除 | ✅ 已修复 |
| 后端路由中文路径 | 框架 | 已全部使用英文 prefix 和 path | ✅ 已验证 |
| models.json 配置化 | 框架 | 已落盘，JSON 驱动模型配置 | ✅ 已验证 |

### 旧 /api/chat/ 兼容路由删除

2026-06-16 完成 —— 从 `backend/app/routers/system.py` 删除了 4 条旧 `/api/chat/` 路由：

- `GET /api/chat/sessions` → 已移除 （改用 `/api/agent/sessions`）
- `POST /api/chat/sessions` → 已移除 （改用 `/api/agent/sessions`）
- `GET /api/chat/sessions/{sid}/messages` → 已移除 （改用 `/api/agent/sessions/{id}/messages`）
- `POST /api/chat/sessions/{sid}/stream` → 已移除 （改用 `/api/agent/sessions/{id}/stream`）

**验证结果：**
- OLD `/api/chat/sessions` → HTTP 404 `{"success":false,"error":"Not Found"}` ✅
- NEW `/api/agent/sessions` → HTTP 200 `{"success":true,"total":33}` ✅

**清理的死亡 import：** `import json`, `StreamingResponse`, `DEFAULT_AGENT_MODEL`, `gateway_router`, `get_current_user`, `LOCAL_CHAT_PROFILE`, `LOCAL_CHAT_ALIASES`

**理由：** 前端没有引用 `/api/chat/` 的任何代码，所有功能已被 `/api/agent/sessions/*` 完全覆盖。旧路由是 V1 遗留的兼容层，属于死代码。

### 剩余的非框架问题

无。`05_移除转中文使类型系统对齐.md` 中记录的问题用户确认晚点自己处理。

## 05_移除转中文使类型系统对齐 — 完成状态

### 背景

`frontend/src/shared/api/response-transform.ts` 中的 `转中文()` 函数在 Axios 响应拦截器里把 API 返回的英文字段名翻译成中文，导致 TypeScript 严格模式下 23 个类型错误全部是字段名不匹配。

### 改动

1. **移除响应拦截器中的 `转中文()` 调用** — `index.ts` 拦截器直接透传原始 JSON，不再做中文化转换
2. **保留 `转中文()` 函数本体但不调用** — `response-transform.ts` 中函数保留，仅在 UI 展示层可手动调用
3. **更新 consumer 文件** — `app-loader.ts` 读 `entry_component_key`，`user.ts` 读 `res.data.user` 等英文字段

### 验证

| 检查项 | 结果 |
|--------|------|
| `vue-tsc --noEmit` | ✅ 零错误通过 |
| `vite build` | ✅ 成功构建 (323ms) |
| `转中文()` 被拦截器调用 | ✅ 已移除 — 拦截器直接透传原始 JSON |
| `转中文()` 外部引用 | ✅ 无 — 仅在自身文件中定义，无任何其他文件引用 |
| `as any` 绕过 | 0 处 |
| `@ts-ignore` / `@ts-expect-error` | 0 处 |

### 结论

`转中文()` 移除完成，类型系统对齐。未来新增模块无需面对遗留类型噪音。
