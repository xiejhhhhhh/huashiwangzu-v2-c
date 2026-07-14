# 底层开发文档

## 后端架构

FastAPI + SQLAlchemy (async) + asyncpg + Pydantic。

### 目录结构

```
backend/app/
├── main.py              应用入口 + lifespan
├── config.py            环境配置（.env 读取）
├── database.py          DB 引擎 + session 工厂
├── gateway/             模型网关（路由/adapter/provider/重试/用量）
├── models/              SQLAlchemy ORM 模型
├── routers/             平台路由（registry.py 统一注册）
├── services/            平台服务层
├── middleware/          鉴权、日志、CORS
└── task_worker_main.py  后台任务调度进程
```

### 模块路由注册

`routers/registry.py` 扫描所有 `modules/*/manifest.json`，动态 import 每个模块的 `backend/router.py` 并挂到 FastAPI app 上。前缀由 manifest 的 `route_prefix` 决定。

### 模型网关

`backend/app/gateway/` 是统一模型调用入口：
- `config.py` — 读 `data/config/models.json`，暴露 profile/provider 配置
- `router.py` — `ModelGatewayRouter` 类，负责选 provider + 重试 + fallback
- `adapters/` — 各模型返回格式适配（deepseek/gemma/openai_compat/qwen）
- `openai_provider.py` — 支持 chat_completions 和 responses 两种协议

### 后台任务

- 表：`framework_system_task_queues`
- 调度：`services/task_dispatcher.py`（单 leader 竞选 + advisory lock）
- 模块注册 handler：`register_task_handler(task_type, async_handler)`
- 发布任务：`publish_task(task_type, parameters, module, priority, ...)`
- 配置：`data/config/task_worker.json`（max_executors/超时/暂停列表）

### 鉴权

JWT token，`/api/login` 获取。middleware 校验后注入 User 对象。
角色：admin > editor > viewer。

## 改动边界

平台改动只动 `backend/app/`，不动 `modules/`。
