# 模块开发文档

业务能力只在 `modules/{key}/`。跨模块禁止直接 import 或读写他表。

## 1. 模块结构

```text
modules/{key}/
├── manifest.json
├── frontend/index.vue
├── backend/router.py          # export 名必须是 router
├── runtime/index.ts           # 可选
└── sandbox/                   # 可选独立沙箱
```

新产品壳也可落在 `products/{id}/`（`product.json` + frontend），由 Product Catalog 暴露到桌面。

桌面内模块/产品前端：

- 必须声明 `uiContract.kit = "mac-app-v1"`（`scan-products` 门禁）
- 入口布局用 `MacAppShell`（`@/desktop/app-kit`），反馈用 `useAppFeedback`
- **模块 backend 禁止依赖前端皮肤或下发 CSS/组件名当业务逻辑**

## 2. manifest 关键字段

| 字段 | 说明 |
|------|------|
| `key` | 模块唯一标识（目录名） |
| `name` | 显示名 |
| `route_prefix` | 后端前缀，如 `/api/knowledge` |
| `backend.router` | router 相对路径 |
| `permissions` | 角色列表 |
| `show_in_launcher` | 是否进启动器（旧路径兼容字段） |
| `product_status` | core / active / background / demo |

桌面可见性以 Product Catalog 为准；旧 apps 清单不再作为正式主路径。

## 3. Capability

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

调用：

- 前端：`platform.modules.call(module, action, params)` 或 `/api/modules/call`
- 后端：`call_capability(module, action, params, caller)`

## 4. 知识库模块（调用摘要）

目录：`modules/knowledge/`

### 4.1 检索

- Capability / API：`search`
- 实现：`backend/services/search_service.py::hybrid_search`
- 默认 `use_rerank=True`（bge-reranker）
- 重排后阈值：`RERANK_SCORE_THRESHOLD = 0.3`（可调优）

### 4.2 管线

- 阶段任务：`kb_pipeline_stage` 等，经统一调度器分发
- 语义层（fusion / profile / graph）依赖模型路由；预算不足应 deferred，不假绿
- 运维巡检可用 toolkit：`knowledge_pipeline_snapshot` / `knowledge_pipeline_node_status` / `knowledge_pipeline_submit`

### 4.3 实体与图谱

当前主路径仍偏“页级 LLM 抽取”。
**规则优先 + 评分路由分层**方案未落地，见临时文档 `03_规则优先实体抽取_待落地_20260718.md`。

## 5. 当前模块族（摘要）

- 核心：`agent`、`knowledge`、`memory`
- 内容相关：各 parser、viewer、office/text/media 产品
- 工具：browser / web / terminal / codemap 等
- 媒体：image-gen / image-vision / media-*

完整清单以仓库 `modules/*` 与 `products/*` 为准。

## 6. 改动边界

- 只改本模块目录
- 需要平台能力：走 framework API / capability
- 需要桌面入口：改 `products/{id}/product.json`（含 `uiContract`）或平台注册，不在模块里硬挂壳层
