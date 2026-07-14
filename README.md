# 华世王镞 V2

桌面式企业 AI 工作台。前端模拟桌面环境（窗口、任务栏、启动器），后端统一管理文件、权限、模型网关和后台任务，业务功能全部做成可插拔模块。

## 启动

```bash
# 后端（含 watchdog 自动重启）
./scripts/start_backend.sh

# 前端开发服务器
cd frontend && npm run dev

# 向量模型（qwen3-embedding-8b，按需）
# 由 watchdog 自动拉起，或手动执行 scripts/models/serve_qwen3_embedding.py
```

## 端口

| 端口 | 服务 |
|------|------|
| 33000 | 后端 FastAPI |
| 5173 | 前端 Vite |
| 30000 | bge-m3 嵌入（deprecated） |
| 30001 | bge-reranker |
| 30002 | qwen3-vl 视觉 |
| 30003 | gemma-4 文本 |
| 30004 | qwen3-embedding-8b（4096D，主力嵌入） |
| 50936 | 本地 gpt-5.5 代理（知识库分析） |

## 目录结构

```
frontend/    Vue 3 桌面壳（Element Plus + TypeScript + Vite）
backend/     FastAPI 平台层（SQLAlchemy async + PostgreSQL + pgvector）
modules/     业务模块（约 35 个，各自含 manifest.json + frontend/ + backend/）
dev_toolkit/ 开发工具 MCP 服务（诊断/SQL/日志/部署）
开发文档/    开发规范和当前方案
```

## 核心机制

- **模块注册**：`modules/*/manifest.json` 声明路由前缀、权限、后端 router 路径
- **跨模块调用**：`/api/modules/call`，走 capability registry，不允许直接 import
- **模型网关**：`backend/data/config/models.json` 是模型配置单一数据源
- **后台任务**：`framework_system_task_queues` 表 + task_dispatcher 调度
- **统一响应**：`{ "success": true, "data": ..., "error": ... }`
