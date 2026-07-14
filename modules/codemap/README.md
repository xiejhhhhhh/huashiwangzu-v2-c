# codemap — 代码地图

Code map module for repository impact lookup, boundary checks, locks, search, metrics, and inaccuracy feedback.

## 对外能力

| 能力 | 说明 |
|------|------|
| `acquire_lock` | 获取文件锁 |
| `check_boundary` | 检查文件或模块的边界合规性，返回违反隔离铁律的引用清单。 |
| `check_lock` | 检查文件锁状态 |
| `get_file` | 查询文件的代码地图信息：所属层/模块、语言、符号清单、依赖与被依赖、注册/调用的能力、涉及的表。 |
| `impact` | 查询影响面：正向（我依赖谁）+ 反向（谁依赖我）的传递闭包，返回波及的文件、模块、跨模块能力清单和风险等级。 |
| `list_feedback` | 列出 codemap 反馈记录 |
| `list_locks` | 列出所有活跃文件锁 |
| `module_map` | 查询模块的对外能力、依赖的外部能力、边界健康状态。 |
| `rebuild` | 全量重建代码索引 |
| `release_lock` | 释放文件锁 |
| `report_inaccuracy` | 报告 codemap 查询结果与实际不符。Agent 实读验证后发现不准时调用。 |
| `search` | 按关键词模糊搜索文件和符号。 |
| `stats` | 返回索引规模、构建耗时、最后更新时间、解析 confidence、反馈样本数与 empirical_accuracy 状态。 |

## 接口

后端前缀：`/api/codemap`

| 路径族 | 方法 |
|------|------|
| /check-boundary | POST |
| /get-file | POST |
| /health | GET |
| /impact | POST |
| /module-map | POST |
| /rebuild | POST |
| /search | POST |
| /stats | GET |

## 数据表

| 表名 |
|------|
| `codemap_feedback` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/codemap/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module codemap --check
```
