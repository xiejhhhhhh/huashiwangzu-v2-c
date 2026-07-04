# Agent 证据引用点击回源闭环收口

时间：2026-07-04

执行者：codex-agent-evidence-clickback-r1

## 本次收口

- 后端 `multi_agent_summary` 聚合保留证据引用 metadata，并补齐 step `input_ref` / `output_ref` 来源的引用扫描。
- 前端新增统一证据引用卡片，展示引用类型、id、来源工具、状态。
- `file_id` / `source_file_id` 通过 Agent 现有 runtime API helper 带鉴权下载为 blob 后打开，避免裸 `/api/files/download/{id}` 丢 Authorization。
- `package_id`、`artifact_id`、`document_id`、`chunk_id`、`page` 显示“暂不可直接打开”及原因说明，不直接读取 Knowledge/Content 表。
- Workflow 详情页的子代理摘要、账本 step/tool/artifact/verification/failure 均接入证据卡片。
- 聊天工具结果卡片复用同一证据卡片，并保留 SSE `references` / `result_ref` 元数据。

## 验证

```bash
backend/.venv/bin/ruff check modules/agent/backend
backend/.venv/bin/python -m pytest modules/agent/backend/tests/test_workflow_service.py -q
backend/.venv/bin/python -m pytest modules/agent/sandbox/test_module.py -q
cd frontend && npm run build
```

结果：

- ruff 通过。
- workflow service 测试 12 passed。
- agent sandbox 测试 20 passed。
- frontend build 通过，仅保留既有 chunk size warning。
- `agent:list_workflows` 活栈能力调用返回 200。

## 边界说明

- 本轮改动只落在 `modules/agent/` 和本收口文档。
- 未修改 `backend/app/`、`frontend/src/`、`modules/knowledge/backend/` 或 `backend/app/services/content/`。
- 相关后端聚合路径未直接读 Knowledge/Content 表，仅处理 Agent 自己账本中的引用 metadata。
- 前端扫描未发现 `any`、`as any`、`@ts-ignore`、`@ts-expect-error`。

## 残留

当前活栈 `list_workflows` 返回空列表，因此没有现成含引用 workflow 可做真实 UI 点击截图。引用数据路径由服务层测试覆盖，前端渲染/类型接线由 `npm run build` 覆盖。
