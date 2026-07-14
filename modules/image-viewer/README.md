# image-viewer — 图片查看器

图片在线查看器，支持 png/jpg/gif/webp/svg 等常见格式。

## 接口

纯前端模块，无后端接口。

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
# No backend sandbox test for this module
cd modules/image-viewer/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-viewer --check
```
