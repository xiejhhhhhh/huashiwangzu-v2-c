# 执行信：Agent 证据引用点击回源闭环

## 目标

在 Agent 已能汇总工具/产物/引用后，把 file_id、document_id、chunk_id、page、package_id、artifact_id 变成用户可点击的证据入口。

## 边界

只允许：

```text
modules/agent/backend/
modules/agent/frontend/
modules/agent/sandbox/
modules/agent/README.md
开发文档/项目记忆/
```

禁止：

```text
backend/app/
dev_toolkit/
modules/knowledge/backend/
backend/app/services/content/
```

## 必做

1. Agent 前端引用卡片显示引用类型、id、来源工具、状态。
2. file_id 可跳文件/桌面打开入口；package_id/artifact_id/document_id 如无直接入口，要显示“暂不可直接打开”的原因。
3. 不直接读 Knowledge/Content 表；只使用已有 runtime/framework 能力。
4. 后端 summary 输出保留 reference metadata，前端类型无 any/as any。

## 验收

```bash
backend/.venv/bin/ruff check modules/agent/backend
backend/.venv/bin/python -m pytest modules/agent/sandbox/test_module.py
cd frontend && npm run build
```

活栈：

```text
agent:list_workflows
含引用的 workflow/tool_call 在前端可见引用卡片
```

## 交付

写：

```text
开发文档/项目记忆/Agent证据引用点击回源闭环收口.md
```

调用：

```text
finish_task(module_key="agent", ...)
memory_write(agent="codex-agent-evidence-clickback-r1")
mcp_feedback(agent="codex-agent-evidence-clickback-r1")
```

## 提示词

请读取并执行：‘/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-Agent证据引用点击回源闭环.md’
