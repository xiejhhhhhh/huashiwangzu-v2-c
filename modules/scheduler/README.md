# scheduler — 定时任务

定时任务：创建/列出/取消，到期自动执行并把结果推到本人 IM。

## 对外能力

| 能力 | 说明 |
|------|------|
| `cancel` | 取消自己创建的定时任务 |
| `create` | 创建定时任务：传入标题、时间/周期、动作描述，到期自动执行并推送结果到本人 IM |
| `list` | 列出自己创建的定时任务 |

## 接口

后端前缀：`/api/scheduler`

| 路径族 | 方法 |
|------|------|
| /cancel | POST |
| /create | POST |
| /list | GET |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/scheduler/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module scheduler --check
```
