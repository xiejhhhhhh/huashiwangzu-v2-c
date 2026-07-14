# docs-open — 文档开放接口

文档统一打开/编辑对外接口，托管文档级访问 token，路由到 office-gen 完成创建/内容读写/导出。

## 对外能力

| 能力 | 说明 |
|------|------|
| `create_doc` | Create a new empty document |
| `get_content` | Get structured JSON content of a document |
| `open` | Open a document by file_id, returns embed_url and content info |

## 接口

后端前缀：`/api/docs`

| 路径族 | 方法 |
|------|------|
| /embed | GET |
| /open | POST |
| /token | POST |

## 数据表

| 表名 |
|------|
| `docs_open_token` |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/docs-open/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module docs-open --check
```
