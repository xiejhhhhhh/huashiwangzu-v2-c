# 华世王镞 V2 开发文档

这是当前开发入口。本文只保留当前事实和导航；历史流水、任务提示、审计原文和工具反馈不作为项目文档保留。

## 项目定位

华世王镞 V2 是干净架构重建：桌面壳 + 平台服务层 + 可插拔业务模块。

```text
frontend/   Vue 桌面壳：登录、桌面、窗口、任务栏、启动器、模块加载、文件打开调度
backend/    FastAPI 平台层：鉴权、数据库、文件、任务、模型网关、模块注册、统一 API
modules/    业务模块和桌面应用：经 manifest/runtime/API 接入主壳
开发文档/    当前规范和开发手册
```

V1 只读参考：`../华世王镞_v1/`。缺能力时可参考 V1 行为，但必须按 V2 架构重建。

## 技术事实

| 项 | 当前口径 |
|---|---|
| 前端 | Vue 3 + vue-router + Pinia + Vite + TypeScript + Element Plus |
| 前端统一 API | `frontend/src/shared/api/index.ts`，Axios + token 注入 + envelope 解包 |
| 模块 runtime | `modules/*/runtime/index.ts`，通过平台 runtime 调 auth/files/office/gateway/tasks/modules 等能力 |
| 后端 | FastAPI + SQLAlchemy async + Pydantic |
| 数据库 | PostgreSQL 17 + pgvector，库名 `华世王镞_v2` |
| 后端端口 | watchdog 固定 `33000`，实际端口见 `backend/logs/.backend.port` |
| 前端端口 | Vite dev server `5173` |
| 嵌入服务 | bge-m3 OpenAI-compatible `/v1/embeddings`，端口 `30000` |
| 登录 | `/api/login` 返回 `data.access_token` |
| 统一响应 | `{ "success": true, "data": ..., "error": ... }` |
| 跨模块调用 | `/api/modules/call` body 字段为 `target_module/action/parameters` |
| 代码索引 | 首选 CodeGraph；再用 codemap；最后 grep/read |
| 工具台 | `.mcp.json` 启动 `python3.14 dev_toolkit/server.py` |

## Agent Handoff

| 需要 | 文档 |
|---|---|
| 开工入口 | `开发文档/agent_handoff/START_HERE.md` |
| 当前状态 | `开发文档/agent_handoff/CURRENT_STATE.md` |
| 稳定契约 | `开发文档/agent_handoff/CONTRACTS.md` |
| 验收门禁 | `开发文档/agent_handoff/ACCEPTANCE.md` |
| 工具台流程 | `开发文档/agent_handoff/TOOLKIT_WORKFLOW.md` |
| 修改边界 | `开发文档/agent_handoff/CHANGE_POLICY.md` |
| 故障诊断 | `开发文档/agent_handoff/TROUBLESHOOTING.md` |
| 模块地图 | `开发文档/agent_handoff/MODULE_MAP.md` |

## Task Docs

| 任务 | 先读 |
|---|---|
| 桌面壳、窗口、模块加载、前端平台能力 | `开发文档/01_框架开发文档/README.md` |
| 后端平台、数据库、权限、任务、文件、模型网关 | `开发文档/02_底层开发文档/README.md` |
| 模块开发、模块边界、manifest/runtime | `开发文档/03_模块开发文档/README.md` |
| 具体模块 | `modules/{module}/README.md` |
| Agent engine 调优 | `开发文档/算法调优手册.md`、`modules/agent/README.md` |
| 工具台使用/升级 | `dev_toolkit/README.md` |

## 架构边界

框架能力属于 `frontend/` 或 `backend/`；业务能力属于 `modules/`。

模块任务只允许改 `modules/{当前模块}/`。模块可以调用框架公开能力，但不能修改 `backend/app/`、`frontend/src/` 或其他模块。跨模块调用必须走统一通路：前端 `platform.modules.call/capabilities`，后端 `/api/modules/call` + capability registry。

## 常用验证

```bash
cd frontend && npm run build
cd backend && .venv/bin/python -m pytest
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
python3.14 dev_toolkit/module_sandbox_matrix.py --json
```

文档和代码事实同步用 `docs_audit` / `docs_sync`。能由 manifest/routes/capabilities/db_schema 查到的事实，不在 README 中手写长篇。
