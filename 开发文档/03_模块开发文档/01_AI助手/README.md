# AI 助手

> ⚠️ **此模块尚未创建。**
> 以下内容是设计参考，描述目标状态。当前 `modules/` 仅保留 `_template/`，不包含 `ai-assistant` 目录。
> 实际实现时，请复制 `modules/_template/` 并按最新规范创建，本 README 在模块创建后需更新为真实状态。

## 模块目标

AI 助手是桌面里的对话与工具调用模块，目标路径：

```text
modules/ai-assistant/
```

## 当前真实状态

- 当前不保留 `modules/ai-assistant/` 目录，AI 助手业务模块已移除占位，后续按 `modules/_template/` 重新创建。
- 当前桌面壳不注册 AI 助手入口；创建 `modules/ai-assistant/manifest.json` 前，前端扫描和后端应用清单同步都不会生成 AI 助手应用。
- 后端模块代码已从平台层清理：`backend/app/services/agent/` 和 `backend/app/routers/agent_*.py` 已删除。
- 模型网关已迁至 `backend/app/gateway/`（框架层 AI 基础设施），支持 DeepSeek/OpenCode/OpenAI 兼容协议，含指数退避重试。
- 默认模型为 `deepseek-v4-flash`，配置在 `backend/app/core/defaults.py` 的 `DEFAULT_CHAT_MODEL`。
- `backend/app/routers/system.py` 中旧 `/api/chat/.../stream` 兼容入口已移除。
- 模块尚未重建；前端入口、runtime、sandbox 和后端 router 均待按模块规范重新创建。

## 当前定位

AI 助手负责用户对话、上下文拼接、模型网关调用、工具调用展示和错误恢复。

模型调用统一通过 `backend/app/gateway/` 网关层，AI 助手不直接调用 provider。

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

## 待办

- 复制 `modules/_template/` 创建 `modules/ai-assistant/`，补齐 `manifest.json`、`frontend/`、`runtime/`、`sandbox/`。
- 创建模块 `backend/router.py`，导出 `router = APIRouter(prefix="/api/agent")`，并在 manifest 的 `backend.router` 中声明。
- 实现会话管理、消息发送、流式响应等核心功能。
- sandbox 自测通过后接入主桌面壳。
