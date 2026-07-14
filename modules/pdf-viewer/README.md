# pdf-viewer — PDF 查看器

PDF 在线查看器。

## 接口

纯前端模块，无后端接口。

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/pdf-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module pdf-viewer --check
```
