# ppt-viewer — 演示文稿查看器

演示文稿在线查看器，支持 pptx/ppt 格式。

## 接口

纯前端模块，无后端接口。

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/ppt-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module ppt-viewer --check
```
