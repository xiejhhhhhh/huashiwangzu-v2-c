# 底层开发文档

平台后端在 `backend/app/`。模块不得直连彼此实现或表。

## 1. 架构

```text
backend/app/
├── main.py                 入口 + lifespan（含 content schema 幂等补齐）
├── config.py / database.py 配置与异步引擎
├── gateway/                模型网关（唯一模型调用入口）
├── contracts/              内容/摄取等跨层契约
├── models/                 SQLAlchemy ORM
├── routers/                平台路由（registry 动态挂模块）
├── services/               平台服务（文件/桌面/内容/产品/任务…）
├── middleware/             JWT / CORS / 日志
└── task_worker_main.py     后台任务进程
```

技术栈：FastAPI + SQLAlchemy async + asyncpg + Pydantic。
库：PostgreSQL 17 + pgvector。表前缀：`framework_*` / 模块自有前缀。

## 2. 模型网关

目录：`backend/app/gateway/`

职责：调用方只报用途，网关选模型、协议、降级与流式归一。

| 件 | 作用 |
|----|------|
| `config.py` | 读 `backend/data/config/models.json` |
| `router.py` | 选 provider、重试、fallback |
| `openai_provider.py` | chat / responses 协议 |
| `anthropic_provider.py` | Anthropic messages 协议 |
| `adapters/*` | 上游事件 → 统一 `StreamEvent` |

统一流式事件类型：`token / thinking / tool_call / done / error`。
前端只消费归一后的 SSE，不感知上游协议差异。

当前路由习惯（以 `models.json` 为准，改后需重启或 reload）：

```text
Agent 对话          → deepseek-v4-flash (opencode)
Agent 视觉/生图     → gpt-5.5 via jayce
知识库文本阶段      → deepseek-v4-flash（优先）
知识库视觉阶段      → gpt-5.5 via jayce → qwen3-vl
向量嵌入            → qwen3-embedding-8b
重排序              → bge-reranker
```

注意：知识库侧历史熔断层与网关并存时可能“打架”；收口进度见临时文档 `02_底座未完成收口清单_20260718.md`。

## 3. 内容与产品平台服务

| 能力 | 入口 |
|------|------|
| Product Catalog | `services/product_catalog_service.py` + `routers/products.py` |
| Content Open | `services/content_open_resolver.py` + `routers/content_open.py` |
| Content Runtime | `services/content/content_runtime_service.py` |
| Canonical IR | `contracts/canonical_content_ir.py` + `services/content/canonical_normalizer.py` |
| 异步摄取 | `services/content/ingestion_*` + 任务类型 `content_ingest_stage` 等 |
| Schema 幂等补齐 | `services/content_runtime_schema.py`（`main.py` lifespan 调用） |
| 桌面状态 CAS | desktop state + `expected_version` |

## 4. 后台任务

- 表：`framework_system_task_queues`
- 调度：`services/task_dispatcher.py`（单 leader + lease/heartbeat）
- 注册：`register_task_handler(task_type, handler)`
- 发布：`publish_task(task_type, parameters, module, priority, ...)`
- 配置：`backend/data/config/task_worker.json`

常用知识库任务类型：`kb_pipeline_stage`、`kb_chunk_embedding_backfill`、`kb_enterprise_import` 等。

## 5. 鉴权

- `POST /api/login` 取 JWT
- middleware 注入用户；角色 `admin > editor > viewer`
- capability / 路由用 `min_role` 门禁

## 6. 验证

```bash
cd backend && .venv/bin/python -m pytest
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui
```

## 7. 改动边界

只改 `backend/app/` 与平台配置；业务逻辑进 `modules/{key}/`。
