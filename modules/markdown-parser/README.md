# markdown-parser — Markdown Parser

解析 Markdown 文件为统一内容块，保留标题层级。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse Markdown files into unified content blocks with heading levels |

## 接口

后端前缀：`/api/markdown-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/markdown-parser/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module markdown-parser --check
```
