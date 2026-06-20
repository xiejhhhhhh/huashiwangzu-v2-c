# Knowledge Module

知识库模块是 Agent 的可选插件。它把框架文件系统中的资料登记为知识库文档，调用格式解析模块生成统一内容块，完成分块、向量化、混合检索、页级融合、实体词典、知识图谱和治理候选管理，并通过框架跨模块能力注册表向 Agent 暴露检索技能。

## Capabilities

| Capability | Description | Parameters |
| --- | --- | --- |
| `knowledge:search` | Hybrid keyword/vector search over indexed chunks | `query`, `top_k` |
| `knowledge:get_block` | Read a specific content block | `block_id` |
| `knowledge:get_page_fusion` | Read fused page content | `document_id`, `page` |
| `knowledge:get_entity_dictionary` | Query extracted entity dictionary | `keyword` |
| `knowledge:get_graph_context` | Query graph nodes and edges around an entity | `entity_id` |
| `knowledge:get_pending_count` | Count pending governance candidates | none |
| `knowledge:get_evidence_detail` | Query evidence records for an entity | `entity_id` |

Agent discovers these automatically as function tools named `knowledge__search`, `knowledge__get_block`, etc.

## Backend APIs

| Method | Path | Description |
| --- | --- | --- |
| `GET` | `/api/knowledge/health` | Module health |
| `POST` | `/api/knowledge/documents` | Register a framework file into knowledge base |
| `GET` | `/api/knowledge/documents` | List registered documents |
| `GET` | `/api/knowledge/documents/{id}` | Document detail |
| `DELETE` | `/api/knowledge/documents/{id}` | Soft delete document |
| `POST` | `/api/knowledge/documents/parse` | Parse, chunk, embed, fuse pages, and optionally extract graph |
| `POST` | `/api/knowledge/search` | Hybrid search |
| `GET` | `/api/knowledge/documents/{id}/chunks` | Read document chunks |
| `GET` | `/api/knowledge/chunks/{id}` | Read chunk detail |
| `GET` | `/api/knowledge/documents/{id}/page/{page}` | Read page fusion |
| `GET` | `/api/knowledge/entities` | Query entity dictionary |
| `GET` | `/api/knowledge/entities/{id}/graph` | Query graph context |
| `GET` | `/api/knowledge/entities/{id}/evidence` | Query evidence details |
| `GET` | `/api/knowledge/governance/candidates` | List governance candidates |
| `POST` | `/api/knowledge/governance/candidates/{id}/approve` | Approve candidate |
| `POST` | `/api/knowledge/governance/candidates/{id}/reject` | Reject candidate |
| `POST` | `/api/knowledge/governance/entities/merge` | Merge entities |
| `POST` | `/api/knowledge/governance/calibrate` | Calibrate extraction |
| `GET` | `/api/knowledge/governance/pending-count` | Pending count |

## Tables

All tables are module-owned and use the `kb_*` prefix. They do not add database foreign keys to framework tables or other modules.

| Table | Purpose |
| --- | --- |
| `kb_catalogs` | Knowledge catalog tree |
| `kb_documents` | Registered document metadata and parse/index status |
| `kb_chunks` | Chunked parsed content and JSON embeddings |
| `kb_page_fusions` | Page-level fused text |
| `kb_entity_dictionary` | Entity dictionary |
| `kb_entity_aliases` | Entity aliases |
| `kb_disambiguation` | Ambiguous term candidates |
| `kb_graph_nodes` | Knowledge graph nodes |
| `kb_graph_edges` | Knowledge graph relations |
| `kb_chunk_entities` | Chunk-to-entity links |
| `kb_evidence` | Source evidence excerpts |
| `kb_conclusion_evidence` | Conclusion evidence chains |
| `kb_entity_merge_log` | Entity merge history |
| `kb_governance_candidates` | Governance review candidates |

## Parser Dependencies

The module does not parse formats directly. It calls parser modules through the framework capability registry:

| Format | Capability |
| --- | --- |
| PDF | `pdf-parser:parse` |
| DOCX | `docx-parser:parse` |
| PPTX | `pptx-parser:parse` |
| XLSX/CSV | `xlsx-parser:parse` |
| TXT/MD | `text-parser:parse` |
| Image | `image-vision:describe` |

Every parser reads framework files through `check_file_access`; knowledge only stores `file_id` and parsed products.

## Sandbox

The sandbox uses the real framework database, file storage, model gateway, and parser modules. It loads `backend/.env` automatically and creates/touches only `kb_*` tables.

```bash
cd modules/knowledge/sandbox
PYTHONPATH=../../../backend uvicorn backend.main:app --host 127.0.0.1 --port 38050 --reload
npm install
npm run dev
```

Frontend sandbox URL: `http://127.0.0.1:5185`.

Sandbox build check:

```bash
cd modules/knowledge/sandbox
npm run build
```

The sandbox build has been verified. Vite may report chunk-size warnings because the sandbox registers full Element Plus for local development.

## Verification Flow

1. Upload a PDF/DOCX/TXT/MD through the knowledge UI.
2. Register the framework `file_id` into `kb_documents`.
3. Run parse/index to call the matching parser module.
4. Confirm `kb_chunks` and `kb_page_fusions` are populated.
5. Search from `/api/knowledge/search` or call `knowledge:search` via `/api/modules/call`.
6. Open Agent tools and confirm `knowledge__search` appears through capability discovery.

## Boundaries

- All source lives under `modules/knowledge/`.
- Business tables use only `kb_*` names.
- Cross-module calls use the framework module registry; there are no imports from Agent or parser module code.
- File access by `file_id` is delegated to parser modules and framework `check_file_access`; knowledge document registration also validates access through `check_file_access`.
- Shared state is persisted in tables, not in process memory.
