# im — 消息

站内消息：用户间单聊会话、发消息、站内通知、未读数。

## 对外能力

| 能力 | 说明 |
|------|------|
| `notify` | 向用户发送站内通知 |
| `send` | 向现有 IM 对话发送消息 |

## 接口

后端前缀：`/api/im`

| 路径族 | 方法 |
|------|------|
| /conversations | GET/POST |
| /messages | POST |
| /unread-count | GET |
| /users | GET |

## 数据表

| 表名 |
|------|
| `im_conversations` |
| `im_messages` |
| `im_read_state` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/im/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module im --check
```
