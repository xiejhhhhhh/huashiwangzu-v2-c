# email-parser — Email Parser

解析 EML/MSG 邮件文件为统一内容块，含邮件头和正文。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse EML/MSG email files into unified content blocks with headers and body |

## 接口

后端前缀：`/api/email-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/email-parser/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module email-parser --check
```
