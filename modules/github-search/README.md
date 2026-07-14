# github-search — GitHub 搜索

GitHub 开源项目和代码搜索，按活跃度和质量排序，自动过滤归档/不活跃项目。

## 对外能力

| 能力 | 说明 |
|------|------|
| `search` | 搜索 GitHub 开源项目，按活跃度和质量排序。输入关键词即可，自动过滤归档和不活跃项目。 |
| `search_code` | 在 GitHub 上搜索代码片段。返回包含匹配代码的文件路径和仓库信息。 |

## 接口

后端前缀：`/api/github-search`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /search | POST |
| /search-code | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/github-search/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module github-search --check
```
