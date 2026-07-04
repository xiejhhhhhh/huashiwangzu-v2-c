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
| `/documents/{id}/ingest-status` | GET | 查询入库队列与分析阶段状态 |
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
| `knowledge:get_ingest_status` | `document_id` |
| `knowledge:audit_lifecycle_debt` | `limit`, `reason` |
| `knowledge:archive_source_unavailable_documents` | `dry_run`, `limit`, `reason`, `confirm`, `audit_reason` |

## 数据表

所有业务表使用 `kb_*` 前缀：catalogs、documents、chunks、page_fusions、entity_dictionary、entity_aliases、disambiguation、graph_nodes、graph_edges、chunk_entities、evidence、conclusion_evidence、entity_merge_log、governance_candidates。

## 主链路质量契约

- `ingest-status` 是 Agent 和前端判断入库状态的统一口径，必须同时暴露队列任务、源文件可用性、parse/vector/raw/fusion/profile/graph/relation 的阶段摘要。
- 源文件被删除或缺失时，状态必须显示为 `source_unavailable`，不得把历史 `done` 的 raw/fusion/profile 结果继续计入看板完成数。
- 图谱进度以本文档治理候选或 chunk-entity 关联数作为文档级完成信号，同时返回全局 graph node 计数用于诊断；不能只依赖可能为空的中间关联表。
- LLM 调用必须记录 `LLM_CALL_START/END/ERROR` 或流式 TTFT 日志；流式无 fallback 失败必须抛错，不得返回空 content 伪装成功。
- 后台 pipeline 必须把 stage 结果写入 `kb_pipeline_runs` / `kb_pipeline_stage_runs`，失败、降级和 source unavailable 都要能从状态接口或治理能力看到。

## 视频分析规划

知识库视频分析体系建议按“先音频转写 + segment text RAG，再关键帧 OCR，再 VLM segment caption，最后视觉检索和 GraphRAG”的路线演进。详细方案已沉淀到 `开发文档/03_模块开发文档/knowledge_video_analysis_system_plan.md`。

第一版最小闭环目标：上传视频 → 登记为 `kb_documents` → 建立 media asset → 固定 30 秒切 segment → FunASR 转写 → 生成 segment `content_text` → BGE-M3 向量化 → 搜索命中并能跳转到视频时间点。

## Parser 依赖

knowledge 不直接解析文件格式，只通过框架能力调用。所有 parser 产出统一的 **DocumentIr** 中间表示（见 `ir_models.py`），knowledge 的分块、融合、导出只消费 DocumentIr。

| 格式 | 能力 |
|---|---|
| PDF | `pdf-parser:parse` |
| DOCX | `docx-parser:parse` |
| PPTX | `pptx-parser:parse` |
| XLSX | `xlsx-parser:parse` |
| CSV/TSV | `csv-parser:parse` |
| TXT | `text-parser:parse` |
| Markdown | `markdown-parser:parse` |
| JSON/YAML | `structured-parser:parse` |
| EML/MSG | `email-parser:parse` |
| Image | `image-vision:describe` |

### 统一文档中间表示 (DocumentIr)

```python
class DocumentIr(BaseModel):
    file_id: int
    format: str
    blocks: list[ContentBlock]     # 统一内容块
    resources: list[ResourceRef]   # 二进制资源引用
    parse_errors: list[str]        # 空结果/低质量/失败区分

class ContentBlock(BaseModel):
    type: BlockType                # heading/paragraph/table/code/image/...
    text: str
    page: int | None
    hierarchy_level: int           # 标题层级
    children: list[ContentBlock]   # 子节点（嵌套结构）
    coordinate: Coordinate | None  # 坐标（版面分析）
```

### 搜索结果引用口径

Knowledge 搜索和 evidence capability 输出统一使用 Agent EvidenceReference 的同一组字段语义：

```text
source_module=knowledge
file_id/source_file_id
document_id
chunk_id
content_package_id(package_id)
page
section
paragraph
score
title/source_file/snippet
```

Knowledge 只维护 `kb_documents/kb_chunks/kb_page_fusions` 等知识库权威数据；不复制 ContentPackage 全量 IR，也不直接读写 Artifact 表。若需要 ContentPackage 元信息，只保存 `content_package_id` 作为逻辑引用，详情和下载/打开动作交给框架 Content/Artifact/File API 做权限校验后返回。

前端搜索结果卡片与 Agent evidence card 保持同语义：能定位 `source_file_id` 时可打开/下载原文件；任何结果都可复制引用和查看原始 metadata；无法定位时不生成假链接。

### 分块策略

- `fixed_size`：传统段落/句子固定大小分块（向后兼容）
- `title_aware`：按标题边界切分，标题下内容保持在同一块
- `structure_aware`：遵循 DocumentIr 层级，表格/代码块保持完整

### 导出

- `POST /api/knowledge/documents/export` — 导出 Markdown/HTML/JSON
- 导出格式后端强校验，仅允许 `markdown`、`html`、`json`；非法格式返回统一错误，不静默降级。
- 导出内容采用单一 canonical source：优先页级融合 `kb_page_fusions`，没有融合内容时回退 `kb_chunks`，避免 fusion 与 chunk 重复输出。
- 导出结果包含 `document_id`、`title`、`format`、`source_status`、`search_ready`、`deep_ready`、`block_count/evidence_count` 等 metadata。
- 导出依赖 DocumentIr，新增格式自动获得导出能力。

### 用户状态与源文件不可用

- 前端只向用户表达：源文件可用/不可用、可搜索、可深度分析、可导出、图谱可用/暂无数据、治理待办。
- 图谱没有实体或关系时显示“图谱暂无数据”，不作为致命失败；搜索和导出仍按 `search_ready` 判断。
- `source_unavailable` 必须给处理路径：提示去桌面/回收站恢复或重新上传源文件，并提供确认后的删除无效知识记录入口。
- 生命周期治理能力必须默认 dry-run：`knowledge:audit_lifecycle_debt` 返回 source recycled/missing 计数、候选文档和建议动作；`knowledge:archive_source_unavailable_documents` 只有在 `dry_run=false` 且 `confirm="ARCHIVE_SOURCE_UNAVAILABLE"` 时才软归档文档（`kb_documents.deleted=true`），不物理删除 chunks/raw/fusions。

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

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `knowledge`, window `normal`, formats: Not format-bound. |
| Backend capability | PASS | 16 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file APIs or capability bridge; file_id paths must preserve check_file_access. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `knowledge:<action>` and release smoke/capability drift gates. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py
cd modules/knowledge/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module knowledge --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
