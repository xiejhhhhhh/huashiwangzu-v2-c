# 默认使用 deepseek-v4-flash

# 默认使用 deepseek-v4-flash

## 当前发现

- `backend/app/core/defaults.py` 中 `DEFAULT_AGENT_MODEL = "deepseek-v4-flash"`。
- `backend/app/services/agent/gateway/router.py` 中有 `deepseek-v4-flash`、`deepseek-v4-pro`、`gemma-4`、`local-test` 四个 profile。
- `backend/app/routers/system.py` 仍保留旧 `LOCAL_CHAT_PROFILE = "gemma-4"`。
- 旧 deepseek-r1 别名已被移除，但仍需要在 adapter registry 确认无残留。

## 目标

- AI 助手默认模型为 `deepseek-v4-flash`。
- 不再把废弃模型作为默认模型。
- 本地模型只在明确选择时使用。

## 验收

- 新建 AI 助手会话默认请求 deepseek flash。
- 模型选择和实际 gateway profile 一致。

## 完成后归档

完成后把当前默认模型规则合并回本目录 `README.md`，再删除本文件。
