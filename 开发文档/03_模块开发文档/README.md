# 模块开发文档

## 模块结构

```
modules/{key}/
├── manifest.json       模块声明（必须）
├── frontend/
│   └── index.vue       前端入口组件
├── backend/
│   └── router.py       后端路由（APIRouter，export 名必须是 router）
├── runtime/
│   └── index.ts        前端运行时 API 封装
└── sandbox/            独立测试沙箱（可选）
```

## manifest.json 关键字段

| 字段 | 说明 |
|------|------|
| key | 模块唯一标识（目录名） |
| name | 显示名称 |
| route_prefix | 后端路由前缀（如 /api/knowledge） |
| backend.router | router.py 相对路径 |
| permissions | 允许的角色列表 |
| show_in_launcher | 是否显示在启动器 |
| product_status | core/active/background/demo |

## capability 注册

后端 router.py 里用 `register_capability` 注册对外能力：

```python
from app.services.module_registry import register_capability

register_capability(
    module_key="knowledge",
    action="search",
    handler=handle_search,
    description="知识库搜索",
    parameters={"query": {"type": "string"}},
    min_role="viewer",
)
```

Agent 通过 capability_catalog 自动发现并调用。

## 跨模块调用

- 前端：`platform.modules.call(target_module, action, parameters)`
- 后端：`call_capability(module, action, params, caller)`
- **禁止直接 import 其他模块代码或读其他模块的表**

## 当前模块清单（约 35 个）

核心：agent、knowledge、desktop-tools、memory
应用：douyin-delivery、im、wechat-writer、excel-engine、docs-open
工具：browser-tools、web-tools、github-search、terminal-tools、codemap
解析器：pdf-parser、docx-parser、pptx-parser、xlsx-parser、csv-parser、text-parser、email-parser、markdown-parser、structured-parser
媒体：image-gen、image-vision、media-asr、media-intelligence
查看器：doc-viewer、pdf-viewer、ppt-viewer、image-viewer、text-editor
其他：office-gen、scheduler、model-router
