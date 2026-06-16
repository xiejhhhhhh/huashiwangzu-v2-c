# 模块开发文档

## 模块目标

模块是桌面里的软件和插件。业务功能优先放入 `modules/`，不要塞进框架。

每个模块必须先在自己的 `sandbox/` 里完成独立开发和验收，再接入主桌面壳。

## 当前真实状态

- 当前仓库还没有 `modules/` 目录。
- 当前 AI 助手、文件管理、知识库仍未迁入目标模块目录。
- 当前桌面应用清单仍来自 `backend/app/seed_data/apps.json`。
- 当前前端组件映射仍来自 `frontend/src/desktop/app-registry/component-key-map.generated.ts`。
- 当前模块文档已经先按目标模块建立在 `开发文档/03_模块开发文档/` 下。

## 目标模块结构

```text
modules/{module_name}/
  manifest.json
  runtime.config.json
  runtime/
  frontend/
  backend/
  submodules/
  sandbox/
  test-data/
  assets/
  module-docs/
  tests/
```

## 目标 sandbox 门禁

模块开发必须先完成 sandbox 自测，再接入主框架。

```text
modules/{module_name}/sandbox/
  index.html 或 test-entry.vue
  mini-shell.ts
  dev-server.ts
  runtime.config.json
  db-tools.ts
```

未通过 sandbox 的模块，不允许接入桌面壳。

## 目标子模块规则

复杂模块可以拆子模块：

```text
modules/knowledge/submodules/catalog/
modules/knowledge/submodules/ingestion/
modules/knowledge/submodules/retrieval/
modules/knowledge/submodules/qa/
```

子模块由父模块扫描和管理，不进入桌面壳全局扫描。

## 当前测试数据规则

模块测试数据必须：

- 有来源。
- 有标记。
- 有清理脚本。
- 用完清空。

## 模块文档

每个模块目录只保留一个长期 `README.md`。临时方案完成后必须合并回该模块 `README.md`，然后删除临时文档。
