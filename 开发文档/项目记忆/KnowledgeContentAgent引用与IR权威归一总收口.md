# Knowledge / Content IR / Agent 引用权威归一总收口

日期：2026-07-04
执行 agent：codex

## 目标

一次性收口 Knowledge、ContentPackage / Content IR、Agent references / artifacts 三套结构重复问题，明确：

- Content IR 是内容包结构权威。
- Knowledge 是检索、chunk、page fusion、document profile 的知识库权威。
- Agent 只保存轻量证据引用，不复制 Knowledge chunk、Content IR 或 Artifact 全量 metadata。
- Artifact 是文件化产物权威，提供可打开 / 下载入口。

## 最终权威结构

### Content IR / ContentPackage

权威字段：

```text
source_file_id
source_module
parser
blocks
assets/resources
metadata
warnings
quality
```

规则：

- `blocks` 是内容结构权威。
- `assets` 与历史 `resources` 兼容，写库后同时保留，避免 parser / viewer 侧重复造结构。
- `source_file_id` 可由 `write_ir` 参数或 IR body 提供，但写入前必须走框架文件权限校验。
- `source_module/parser/metadata/warnings/quality` 持久化进 ContentPackage version JSON，后续 viewer/export 统一从 ContentPackage 取。

### Knowledge

Knowledge 权威维护：

```text
kb_documents
kb_chunks
kb_page_fusions
kb_document_profiles
kb_file_relations
```

搜索 / evidence 输出统一引用字段：

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

Knowledge 不复制 ContentPackage 全量 IR，不直接读写 Artifact 表；需要关联内容包时只保存 `content_package_id`，详情经框架 Content / Artifact / File API 回源。

### Agent EvidenceReference / Artifact

Agent evidence 引用最小字段：

```text
source_module
file_id/source_file_id
document_id
chunk_id
package_id
artifact_id
page
section
score
title
snippet/excerpt
download_url/open_url
```

规则：

- Agent 不读 `kb_*` 表，不 import Knowledge 代码；Knowledge 来源必须来自 `knowledge:*` capability 返回。
- Agent workflow / message meta 只保存 ID、摘要、打开/下载 URL 等轻量引用。
- Artifact 权威字段是 `artifact_id`、`package_id`、`source_file_id`、`origin_module`、`download_url`、`open_url`。
- Agent workflow artifact 只说明本 workflow 产出或引用了什么，不成为内容权威源。

## 已移除 / 避免的重复结构

- 避免 Agent 复制 Knowledge chunk 正文、文档详情、ContentPackage IR、Artifact 全量 metadata。
- 避免 Knowledge 搜索结果生成假打开链接；没有 `source_file_id` 时只展示 metadata / 引用。
- 避免 Content IR 里 `assets` 和 `resources` 各自发散；统一互为兼容口径。
- 避免 Artifact publish 回包只给局部字段；现在回包携带标准 artifact/file/package/source 线索。

## 跨模块边界保证

- 跨模块信息流继续走框架能力通路：Agent 通过 capability 获取 Knowledge 结果，不直接 import 模块代码或读表。
- 文件打开 / 下载继续走 `/api/files/*`，由框架权限链路校验。
- ContentPackage 写入含 `source_file_id` 时走已有 `check_file_access` 路径。
- 前端展示只消费后端返回的英文真实字段，不用展示翻译函数改变字段名。
- 本次未新增模块间直接数据库访问。

## 前端展示收口

- Agent `EvidenceReferenceList` 统一展示文件、Knowledge document/chunk、ContentPackage、Artifact 引用。
- 支持打开、下载、复制 ID、复制引用、metadata 查看；无法打开时展示明确原因。
- Knowledge 搜索结果卡片使用同一字段语义，支持打开/下载源文件、复制引用、查看 metadata。

## 修改文件

本轮核心修改：

```text
backend/app/services/content/ir_schema.py
backend/app/services/content/ir_validator.py
backend/app/services/content/ir_normalizer.py
backend/app/services/content/ir_writer.py
backend/app/services/artifact_service.py
backend/app/services/content/export_service.py
backend/tests/test_content_ir_architecture.py
backend/tests/test_content_artifact_publish.py
modules/agent/backend/_utils.py
modules/agent/frontend/components/evidenceReferences.ts
modules/agent/frontend/components/EvidenceReferenceList.vue
modules/agent/README.md
modules/knowledge/frontend/index.vue
modules/knowledge/README.md
开发文档/项目记忆/KnowledgeContentAgent引用与IR权威归一总收口.md
```

工作区另有大量既有 dirty / 其他任务变更，本收口不归因、不回滚。

## 验证命令与结果

已通过：

```bash
backend/.venv/bin/python -m ruff check backend/app/services/artifact_service.py backend/app/services/content/export_service.py backend/app/services/content/ir_normalizer.py backend/app/services/content/ir_schema.py backend/app/services/content/ir_validator.py backend/app/services/content/ir_writer.py modules/agent/backend/_utils.py modules/knowledge/backend/router.py
```

```text
PASS
```

```bash
cd backend && .venv/bin/python -m pytest tests/test_content_artifact_publish.py
```

```text
8 passed
```

```bash
cd backend && .venv/bin/python -m pytest tests/test_content_ir_architecture.py
```

```text
58 passed, 1 existing FastAPI deprecation warning
```

```bash
cd backend && .venv/bin/python -m pytest ../modules/agent/backend/tests/test_workflow_service.py
```

```text
13 passed
```

```bash
cd backend && .venv/bin/python -m pytest ../modules/agent/backend/tests/test_workflow_api.py
```

```text
7 passed, 1 existing warning
```

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/knowledge/sandbox/test_module.py
```

```text
15 passed
```

```bash
cd backend && .venv/bin/python -m pytest ../modules/knowledge/backend/tests
```

```text
61 passed, 1 existing warning
```

```bash
npm --prefix frontend run build
```

```text
PASS
```

活栈健康检查：

```text
/api/health: ok, db ok, worker ok, task queue failed/pending/running all 0
```

测试数据污染检查：

```text
active/recycled/knowledge/content/uploads test artifacts all 0
```

## release_gate

```text
release_gate(skip_ui=true, mode=preflight): PASS_WITH_DEBT
blockers: []
release_safe: true
deploy_allowed: true
```

## 剩余债务 / 非阻塞项

- 当前工作区存在大量既有 dirty / untracked 文件，非本轮全部产生；release gate 因 dirty worktree 记为 debt。
- 本次 release gate 使用 `skip_ui=true` / `preflight`，完整 UI smoke、sandbox matrix、model fallback 等仍属于后续完整发布前检查。
- 没有发现阻塞项。
