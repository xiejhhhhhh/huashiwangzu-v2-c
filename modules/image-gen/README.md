# image-gen — Image Generation

Image generation module with provider templates, prompt translation, generation records, and usage history.

## 对外能力

| 能力 | 说明 |
|------|------|
| `generate` | 生成图片：根据提示词生成产品图、海报、配图等；Agent 默认写入工作区草稿，`publish=true` 才进入桌面文件系统 |
| `list_templates` | 列出可用生图模板（服务商+模型），含凭据是否齐全标识 |
| `transform` | 图生图/多图生图：读取已有图片 file_id 数组作为参考图，返回统一 framework file_id |
| `usage_history` | 查询本人的生图历史记录，含积分消耗 |

## 接口

后端前缀：`/api/image-gen`

| 路径族 | 方法 |
|------|------|
| /generate | POST |
| /health | GET |
| /history | GET |
| /templates | GET |
| /transform | POST |

## 数据表

| 表名 |
|------|
| `imagegen_records` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/image-gen/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-gen --check
```
