# 开发文档

## 架构边界

- 框架能力（鉴权/文件/网关/任务/桌面壳）→ `frontend/src/` 或 `backend/app/`
- 业务能力（知识库/Agent/生图/解析器等）→ `modules/{key}/`
- 模块只能改自己目录，跨模块走 capability bus

## 模型路由

单一配置文件：`backend/data/config/models.json`

```
Agent 对话        → deepseek-v4-flash (opencode)
Agent 视觉/生图   → gpt-5.5 via jayce 中转站
知识库文本分析    → gpt-5.5 via 本地 50936 → fallback gemma-4 → ollama
知识库视觉分析    → gpt-5.5 via jayce → fallback qwen3-vl
向量嵌入          → qwen3-embedding-8b (4096D, 30004)
重排序            → bge-reranker (30001)
```

## 模块开发

1. 复制 `modules/_template/` 改名
2. 填 `manifest.json`（key、路由前缀、权限、后端 router 路径）
3. 前端写 `frontend/index.vue`，后端写 `backend/router.py`
4. 跨模块调用用 `register_capability` 注册 + `/api/modules/call` 调用

## 后台任务

- 注册：`register_task_handler(task_type, handler)`
- 发布：`publish_task(task_type, parameters, ...)`
- 配置：`backend/data/config/task_worker.json`（并发/超时/暂停）
- 调度：task_dispatcher 单 leader 竞选，lease + heartbeat

## 数据库

PostgreSQL 17 + pgvector。库名 `华世王镞_v2`。密码在 `backend/.env`。
表命名：框架表 `framework_*`，模块表按模块前缀（`agent_*`、`kb_*`）。

## 验证命令

```bash
cd backend && .venv/bin/python -m pytest          # 后端测试
cd frontend && npm run build                       # 前端编译
python3.14 dev_toolkit/release_gate.py --preflight --skip-ui  # 发布门禁
```

## 子目录说明

| 目录 | 内容 |
|------|------|
| `01_框架开发文档/` | 前端桌面壳、窗口系统、模块加载规范 |
| `02_底层开发文档/` | 后端平台层、数据库、网关、任务调度 |
| `03_模块开发文档/` | 模块开发规范、manifest 字段说明 |
| `临时文档/` | 当前进行中的任务文档（满 9 个归档） |
| `算法调优手册.md` | Agent 引擎参数调优指南 |
