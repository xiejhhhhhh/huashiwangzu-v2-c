# 执行信：Artifact 桌面可见与下载入口闭环

## 目标

在 ContentPackage -> Artifact 发布能力已落地后，让用户能在桌面/文件入口看到、打开、下载已发布 artifact，不只停留在后端记录。

## 边界

允许：

```text
frontend/src/desktop/
frontend/src/shared/components/
frontend/src/shared/api/ 与 artifact/file 展示直接相关文件
backend/app/routers/content.py（仅补读接口/字段，不改发布核心）
backend/app/services/content/（仅必要小修）
frontend/tests/
backend/tests/test_content_artifact_publish.py
开发文档/项目记忆/
```

禁止：

```text
dev_toolkit/release_gate.py
modules/agent/
modules/knowledge/
```

## 必做

1. 发布后的 artifact/file 能在用户可见入口展示。
2. 提供下载/打开入口。
3. 如果 artifact 尚无桌面图标，要至少在内容包详情/文件列表可见。
4. 前端错误态使用已有 ApiError/LoadState 机制。
5. 不破坏 ContentPackage publish 后端契约。

## 验收

```bash
cd frontend && npm run build
backend/.venv/bin/python -m pytest backend/tests/test_content_artifact_publish.py
```

活栈：

```text
content:write_ir -> content:publish -> 前端/文件入口可见 artifact/file
```

## 交付

写：

```text
开发文档/项目记忆/Artifact桌面可见与下载入口闭环收口.md
```

调用：

```text
finish_task(...)
memory_write(agent="codex-artifact-desktop-entry-r1")
mcp_feedback(agent="codex-artifact-desktop-entry-r1")
```

## 提示词

请读取并执行：‘/Users/hekunhua/Documents/Agent/PHP/华世王镞_v2/开发文档/项目记忆/执行信-Artifact桌面可见与下载入口闭环.md’
