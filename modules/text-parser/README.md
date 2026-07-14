# text-parser — Text/Markdown Parser

解析 TXT/MD 文件为统一内容块。

## 对外能力

| 能力 | 说明 |
|------|------|
| `parse` | Parse TXT/MD file into unified content blocks |

## 接口

后端前缀：`/api/text-parser`

| 路径族 | 方法 |
|------|------|
| /health | GET |
| /parse | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/text-parser/sandbox/test_module.py
cd modules/text-parser/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-parser --check
```
