# AI 助手

## 模块目标

AI 助手是桌面里的对话与工具调用模块，目标路径：

```text
modules/ai-assistant/
```

## 当前真实状态

- 当前还没有 `modules/ai-assistant/` 目录。
- 当前 AI 助手后端代码在 `backend/app/services/agent/` 和 `backend/app/routers/agent_*.py`。
- 当前模型网关在 `backend/app/services/agent/gateway/`。
- 当前默认模型是 `deepseek-v4-flash`。
- 当前网关存在 `opencode`、`llama`、`local` provider。
- 当前旧 `/api/chat/.../stream` 兼容入口在 `backend/app/routers/system.py`。
- 当前前端 AI 助手仍通过旧应用组件映射链路加载，不是 `modules/ai-assistant/manifest.json`。

## 当前定位

AI 助手负责用户对话、上下文拼接、模型网关调用、工具调用展示和错误恢复。

## 目标必需功能

- 会话列表和会话详情。
- 消息发送和流式响应。
- 模型网关接入。
- 工具调用过程展示。
- 引用、错误、重试、空状态。
- sandbox 独立调试。

## 目标接入规则

1. AI 助手不得直接绕过平台模型网关。
2. 模型、工具、权限、API 根路径必须通过模块 runtime 获取。
3. 未通过 sandbox 自测前，不接入主桌面壳。
4. 测试会话、测试消息、测试工具调用记录用完必须清理。
