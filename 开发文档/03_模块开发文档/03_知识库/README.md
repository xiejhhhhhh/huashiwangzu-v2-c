# 知识库

## 模块目标

知识库是桌面里的资料编目、抽取、检索、问答、图谱和质量评估模块，目标路径：

```text
modules/knowledge/
```

## 当前真实状态

- 当前还没有 `modules/knowledge/` 目录。
- 当前知识库后端 router 在 `backend/app/routers/knowledge*.py`。
- 当前知识库 model 在 `backend/app/models/knowledge/`。
- 当前知识库 schema 在 `backend/app/schemas/knowledge.py` 和 `backend/app/schemas/knowledge_ext.py`。
- 当前知识库 service 在 `backend/app/services/knowledge/`，已经按 aggregation、candidate、dictionary、evaluation、extract、fusion、graph、label、llm、retrieval、vision 等目录拆分。
- 当前知识库桌面入口仍来自 `backend/app/seed_data/apps.json` 和旧前端组件映射。
- 当前知识库业务还没有经过 `modules/knowledge/sandbox/` 独立验收。

## 当前定位

知识库业务复杂，必须拆成子模块开发。平台提供数据库、队列、模型、文件、权限能力；知识库业务规则、页面、流程和子模块归 `modules/knowledge/`。

## 目标子模块结构

```text
modules/knowledge/submodules/catalog/
modules/knowledge/submodules/ingestion/
modules/knowledge/submodules/retrieval/
modules/knowledge/submodules/qa/
modules/knowledge/submodules/graph/
modules/knowledge/submodules/evaluation/
```

## 目标必需功能

- 资料编目。
- 文件抽取。
- 切片和向量化。
- 检索和 rerank。
- 问答和证据引用。
- 图谱和实体关系。
- 标签、词典、治理。
- 质量评估。
- sandbox 独立调试。

## 目标接入规则

1. 知识库可以调用 `backend/` 的数据库、队列、模型、文件、权限能力。
2. 子模块由知识库父模块扫描和管理，不进入桌面壳全局扫描。
3. 测试文档、测试切片、测试向量、测试问答记录用完必须清理。
4. 未通过 sandbox 自测前，不接入主桌面壳。
