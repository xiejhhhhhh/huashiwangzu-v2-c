# text-editor — 文本编辑器

纯文本在线编辑器，支持 txt/md/json/yaml/xml/ini 等格式。

## 接口

纯前端模块，无后端接口。

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/text-editor/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module text-editor --check
```
