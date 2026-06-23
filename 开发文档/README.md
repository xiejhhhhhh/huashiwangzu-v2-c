# 华世王镞 V2 开发文档

这是项目接手入口。先读本页，再按任务类型进入框架、底层或模块文档。历史过程和批次细节放在 `开发文档/变更历史.md`，本页只保留稳定事实和导航。

## 项目定位

华世王镞 V2 是干净架构重建，不是在旧 Laravel/PHP 树上打补丁。目标形态是桌面壳 + 平台服务层 + 可插拔业务模块，服务内部企业业务场景。

```text
frontend/   Vue 桌面壳：登录、桌面、窗口、任务栏、启动器、模块加载、文件打开调度
backend/    FastAPI 平台层：鉴权、数据库、文件、任务、模型网关、模块注册、统一 API
modules/    业务模块和桌面应用：经 manifest/runtime/API 接入主壳
开发文档/    用户可读的项目文档
```

V1 只作为只读参考：`../华世王镞_v1/`。缺能力时可以查 V1 行为，但必须按 V2 架构重建。

## 技术事实

| 项 | 当前口径 |
|---|---|
| 前端 | Vue 3 + vue-router + Pinia + Vite + TypeScript + Element Plus |
| 前端统一 API | `frontend/src/shared/api/index.ts`，Axios + token 注入 + `{success,data,error}` 解包 + 401/403 处理 |
| 模块 runtime | `modules/*/runtime/index.ts`，提供 `auth/files/office/gateway/tasks/modules` 等平台能力 |
| 后端 | FastAPI + SQLAlchemy async + Pydantic |
| 数据库 | PostgreSQL 17 + pgvector，**由 FlyEnv 集成环境管理**（数据目录 `~/Library/FlyEnv/server/postgresql/postgresql17`），端口 5432，库名 `华世王镞_v2`。homebrew/EDB 两套旧 PG 已禁用自启 |
| 后端端口 | watchdog 固定 `33000`，实际端口以 `backend/logs/.backend.port` 为准 |
| 嵌入服务 | bge-m3 在 **30000**（llama-server，OpenAI 兼容 `/v1/embeddings`），非 8000 |
| 登录 | 端点 `/api/login`（非 /api/auth/login），返回 `data.access_token`。admin `何焜华/123rgE123`，测试 editor/viewer=`admin123` |
| 统一响应 | `{ "success": true, "data": ..., "error": ... }`；能力调用 `/api/modules/call` 字段名是 `parameters`（非 params） |
| 代码索引 | 仓库有 `.codegraph/`，查代码和影响面先用 CodeGraph；codemap 是后端运行时补充能力 |
| 开发工具台 | **`dev_toolkit/` 项目 MCP**（`.mcp.json` 注册），15 工具：brief/probe/call_capability/routes/capabilities/db_schema/tail_log/run_test/lint/code_explore + memory_search/write/recent + smoke。**接手先连它**，详见 `dev_toolkit/README.md` |

## 文档入口

| 任务 | 先读 |
|---|---|
| 桌面壳、窗口、模块加载、前端平台能力 | `开发文档/01_框架开发文档/README.md` |
| 后端平台、数据库、权限、任务、文件、模型网关 | `开发文档/02_底层开发文档/README.md` |
| 模块开发、模块边界、manifest/runtime | `开发文档/03_模块开发文档/README.md` |
| 具体模块 | `modules/{module}/README.md` |
| Agent engine 调优 | `开发文档/算法调优手册.md`、`modules/agent/README.md` |
| 为什么这么改过 | `开发文档/变更历史.md` |

## 模块地图

### AI 与知识

| 模块 | 作用 |
|---|---|
| `agent` | AI 助手：对话、工具发现、上下文引擎、记忆接入、子 Agent、治理面板 |
| `memory` | 事实记忆、语义召回、记忆链、经验库、dream 自优化 |
| `knowledge` | 知识库：文件登记、解析、分块、检索、页级融合、实体图谱、治理候选 |
| `codemap` | 代码地图：影响面、边界检查、文件锁、索引反馈 |

### 工具与自动化

| 模块 | 作用 |
|---|---|
| `terminal-tools` | 用户工作区内执行命令、读写文件、run_python、chart、publish/import |
| `desktop-tools` | 给 Agent 桥接框架文件系统和桌面应用能力 |
| `web-tools` | 联网搜索和网页正文抓取 |
| `office-gen` | 生成 docx/xlsx/pptx/pdf，转换 office 文件 |
| `image-gen` | 生成图片：**多服务商模板适配器架构**（base.py 规范 + providers/{liblib,gptstore,placeholder}）。已接入 **LiblibAI 星流Star-3**（实测可用，key 在 .env），中文 prompt 自动译英，成本记 `imagegen_records`。加服务商=写适配器+加 image_templates.json+加 .env key |
| `scheduler` | 创建、列出、取消定时任务 |
| `im` | 站内消息和系统通知 |
| `docs-open` | 文档开放接口：三件套 token、REST、嵌入编辑器、JSON 中间层 |

### 文件解析、查看与编辑

| 模块 | 作用 |
|---|---|
| `pdf-parser` / `docx-parser` / `pptx-parser` / `xlsx-parser` / `text-parser` | 把文件转统一内容块 |
| `image-vision` | 图片描述 |
| `excel-engine` | 表格编辑器和 XLSX/CSV 文件引擎 |
| `pdf-viewer` / `doc-viewer` / `ppt-viewer` / `image-viewer` | 文件查看器 |
| `text-editor` | 文本和代码文件编辑器 |

### 样板

| 模块 | 作用 |
|---|---|
| `hello-world` | 最小前端样板 |
| `_template` | 新模块模板 |

## 架构边界

框架能力属于 `frontend/` 或 `backend/`；业务能力属于 `modules/`。

模块任务只允许改 `modules/{当前模块}/`。模块可以调用框架公开能力，但不能修改 `backend/app/`、`frontend/src/` 或其他模块。跨模块调用必须走统一通路：前端 `platform.modules.call/capabilities`，后端 `/api/modules/call` + capability registry。禁止模块互相 import 代码或直接读写对方业务表。

## 常用命令

```bash
# 后端(重启后手动拉; 改代码后 kill -9 $(lsof -i :33000 -t) + 清__pycache__ 重启)
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 33000
cd backend && .venv/bin/python -m pytest

# 前端
cd frontend && npm run dev          # 5173, proxy 到 33000
cd frontend && npm run build
cd frontend && npm run scan:modules # 改了组件注册要重扫, 否则桌面壳加载不出模块

# 一键回归(全模块happy-path红绿矩阵)
python3.14 dev_toolkit/smoke.py
# UI 集测
cd frontend && npm run test:browser
```

整数列 server_default 用 `sqlalchemy.text()`（非 func.text()，否则启动崩）。

## 测试铁律（重要）
1. **活栈是常驻夹具，测试只访问不重建**；只有改代码需重置时才重启后端（后端/前端/DB/bge-m3 都是常驻服务）。
2. **登录一次（Playwright storageState）全程复用**，禁每测重登。
3. **条件等待**（waitForSelector/waitForResponse），禁硬等 sleep。
4. **优先直接打活系统黑箱测**（工具台 probe/call_capability），少写测试脚本搭场景。
5. **自测过≠功能对**：验收必须真打活系统（真 HTTP/SQL/浏览器），不只跑单测；报告会被真数据复核，谎报当场抓出。

文档改动无需跑完整测试；代码改动按影响面选择后端 pytest、前端 build、真实登录联调。
