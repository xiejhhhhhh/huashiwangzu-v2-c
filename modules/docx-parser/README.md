# docx-parser — DOCX Parser

解析 DOC/DOCX 文件为统一内容块。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse DOC/DOCX files into unified content blocks |

## 接口

后端前缀：`/api/docx-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/docx-parser/sandbox/test_module.py
cd modules/docx-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docx-parser --check
```
