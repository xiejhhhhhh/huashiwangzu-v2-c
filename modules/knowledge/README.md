# knowledge — knowledge base

knowledge 把框架文件系统中的资料登记为知识库文档，调用 parser 模块生成统一内容块，再做分块、向量化、页级融合、实体词典、知识图谱和治理候选。Agent 通过 `knowledge:*` 能力检索资料。

## 功能

| 功能 | 说明 |
|---|---|
| 文档登记 | 把 framework `file_id` 记录为知识库文档 |
| 解析入库 | 调 PDF/DOCX/PPTX/XLSX/TXT/Image parser，生成 `kb_chunks` |
| 检索 | 关键词 + 向量混合检索，返回内容块和来源 |
| 页级融合 | 把页内内容压成更适合问答的融合文本 |
| 图谱 | 抽取实体、别名、证据、关系，前端用 Three.js 展示 |
| 治理 | 待审核候选、实体合并、校准和 pending count |

## 如何调用

HTTP 前缀：`/api/knowledge`

| 端点 | 方法 | 用途 |
|---|---|---|
| `/documents` | GET/POST | 列出或登记文档 |
| `/documents/{id}` | GET/DELETE | 详情或软删 |
| `/documents/parse` | POST | 解析、分块、向量化、融合、可选图谱 |
| `/search` | POST | 混合检索 |
| `/documents/{id}/chunks` | GET | 文档块列表 |
| `/chunks/{id}` | GET | 块详情 |
| `/documents/{id}/page/{page}` | GET | 页级融合 |
| `/entities` | GET | 实体词典 |
| `/entities/{id}/graph` | GET | 实体周边图谱 |
| `/entities/{id}/evidence` | GET | 实体证据 |
| `/governance/*` | GET/POST | 候选审核、实体合并、校准 |

公开能力：

| 能力 | 参数 |
|---|---|
| `knowledge:search` | `query`, `top_k` |
| `knowledge:get_block` | `block_id` |
| `knowledge:get_page_fusion` | `document_id`, `page` |
| `knowledge:get_entity_dictionary` | `keyword` |
| `knowledge:get_graph_context` | `entity_id` |
| `knowledge:get_pending_count` | none |
| `knowledge:get_evidence_detail` | `entity_id` |

## 数据表

所有业务表使用 `kb_*` 前缀：catalogs、documents、chunks、page_fusions、entity_dictionary、entity_aliases、disambiguation、graph_nodes、graph_edges、chunk_entities、evidence、conclusion_evidence、entity_merge_log、governance_candidates。

## Parser 依赖

knowledge 不直接解析文件格式，只通过框架能力调用：

| 格式 | 能力 |
|---|---|
| PDF | `pdf-parser:parse` |
| DOCX | `docx-parser:parse` |
| PPTX | `pptx-parser:parse` |
| XLSX/CSV | `xlsx-parser:parse` |
| TXT/MD | `text-parser:parse` |
| Image | `image-vision:describe` |

## 边界

- 所有源码在 `modules/knowledge/`。
- 不直接 import Agent 或 parser 模块代码。
- 所有跨模块调用走 `call_capability`。
- 按 `file_id` 读文件必须经过框架 `check_file_access` 或 parser 模块的等价校验。
- 共享状态落库，不依赖 worker 内存。

## 验证

```bash
cd frontend && npm run build
curl -X POST http://127.0.0.1:33000/api/knowledge/search \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"query":"测试","top_k":5}'
```
