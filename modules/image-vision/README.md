# image-vision — Image Vision

图片理解：本地特征分析优先，需要语义细节时才调用视觉模型。

## 对外能力

| 能力 | 说明 |
|------|------|
| `describe` | Analyze image locally first, then use the vision model only when semantic detail is needed |

## 接口

后端前缀：`/api/image-vision`

| 路径族 | 方法 |
|------|------|
| /describe | POST |
| /health | GET |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/image-vision/sandbox/test_module.py
cd modules/image-vision/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module image-vision --check
```
