# douyin-delivery — 抖音内容与计划助手

Douyin delivery module for scripts, ad copy, content validation, delivery task handoff, and cleanup.

## 对外能力

| 能力 | 说明 |
|------|------|
| `cleanup_marked_data` | 按 marker 清理当前用户测试数据（含投递任务 payload/result_payload） |
| `create_delivery_task` | 创建内容交接任务并同步推进可审计状态；不调用外部广告平台 |
| `generate_ad_copy` | 生成广告文案 |
| `generate_script` | 生成抖音口播脚本 |
| `mark_task_failed` | 把交接任务标记为 failed 并写入失败原因 |
| `validate_content` | 知识库校验成分/功效内容 |

## 接口

后端前缀：`/api/douyin-delivery`

| 路径族 | 方法 |
|------|------|
| /accounts | DELETE/GET/POST/PUT |
| /ad-copies | DELETE/GET/POST/PUT |
| /campaigns | DELETE/GET/POST/PUT |
| /cleanup | POST |
| /delivery-tasks | DELETE/GET/POST/PUT |
| /materials | DELETE/GET/POST/PUT |
| /products | DELETE/GET/POST/PUT |
| /prompts | DELETE/GET/POST |
| /scripts | DELETE/GET/POST/PUT |
| /validate | POST |

## 数据表

| 表名 |
|------|
| `douyin_accounts` |
| `douyin_ad_copies` |
| `douyin_campaigns` |
| `douyin_delivery_tasks` |
| `douyin_materials` |
| `douyin_products` |
| `douyin_prompts` |
| `douyin_scripts` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/douyin-delivery/sandbox/test_module.py
cd modules/douyin-delivery/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module douyin-delivery --check
```
