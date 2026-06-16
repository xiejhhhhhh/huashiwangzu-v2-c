# Huashiwangzu V2 Agent Rules

## First Entry

Read this project entry first:

```text
开发文档/README.md
```

Then read the matching documentation by task type:

```text
开发文档/01_框架开发文档/README.md
开发文档/02_底层开发文档/README.md
开发文档/03_模块开发文档/README.md
开发文档/03_模块开发文档/{number_module_name}/README.md
```

## Project Status

- V2 is a clean architecture rebuild, not a patch layer over the old Laravel/PHP tree.
- V1 reference: `../华世王镞_v1/`. It is read-only and must not be modified.
- If a missing capability is needed, inspect V1 or historical versions, then rebuild it under the V2 architecture.
- Target structure: `frontend/ + modules/ + backend/`.

## Architecture Boundary

```text
frontend/   Desktop shell frontend
modules/    Business modules and desktop apps
backend/    Desktop shell backend / platform service layer
```

- Framework capabilities belong in `frontend/` or `backend/`.
- Business capabilities belong in `modules/`.
- Every module must pass its own `sandbox/` validation before integration into the main shell.

## Hard Rules

1. Outside the `开发文档/` documentation tree, every directory name and file name must be English.
2. `开发文档/` is the user-facing documentation tree; Chinese directory names, file names, and prose are allowed there.
3. Markdown documents have no line or word limit.
4. Normal source files should stay within 600 lines; strongly coherent flows may go up to 1000 lines.
5. Python code must use English names, type annotations, and Router -> Schema -> Service -> Model layering.
6. API responses must use the unified JSON shape: `{ "success": true, "data": ..., "error": ... }`.
7. Test data must be cleaned up after use. Whoever creates it is responsible for removing it.
8. Code comments may use Chinese. Markdown prose outside `开发文档/` must use English.
9. Paths, file names, module names, variable names, and configuration names must be English outside `开发文档/`.
10. Do not restore `后端/`, `脚本/`, `部署/`, `backend/_废弃/`, or `backend/脚本/`.
11. Do not commit empty features, temporary comments, or fake-success logic.
12. When a temporary task document is complete, merge the useful result back into the relevant `README.md`, then delete the temporary document.
13. After code changes, run the relevant tests. For backend changes, default to `cd backend && pytest`.

## TypeScript Rules

14. **禁止使用 `any` 类型绕过类型检查。** 未知 API 响应先定义正确接口类型，而非写 `as any` 或 `@ts-ignore`。类型错误就是真 bug，必须修复而非压制。
15. **前端代码访问 API 响应的字段名必须与后端实际返回一致。** 后端返回 `entry_component_key` 则前端也读 `entry_component_key`，不依赖 `转中文()` 转换后的中文名或未定义的 camelCase 别名。若需要映射，在消费侧显式转换，类型定义与运行时必须对齐。
16. **`转中文()` 是 UI 展示层的纯字符串映射工具（下拉文本、toast、按钮文案），不可用于改变字段名或跳过类型检查。** 需访问的数据字段，代码直接读英文名。

## Scan Boundaries

Allowed:

```text
backend/app
backend/tests
frontend/src
modules
开发文档
```

Do not scan:

```text
frontend/node_modules
backend/.venv
backend/venv
.git
__pycache__
*.pyc
```
