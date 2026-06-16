# 框架开发文档

## 框架目标

框架负责桌面壳和平台加载能力，不承载具体业务模块。

目标目录归属：

```text
frontend/   桌面壳前端
backend/    桌面壳后端 / 平台服务层
modules/    被框架加载的业务模块
```

## 当前真实状态

- 当前 `frontend/` 已存在，是 Vue 3 + Vite 桌面壳。
- 当前前端入口是 `frontend/src/main.ts`。
- 当前登录、路由和入口页面在 `frontend/src/app-entry/`。
- 当前桌面窗口、任务栏、启动器、上下文菜单、应用注册表在 `frontend/src/desktop/`。
- 当前平台配置、指令、状态在 `frontend/src/platform/`。
- 当前共享 API、组件、composables、文件关联、上传能力在 `frontend/src/shared/`。
- 当前样式在 `frontend/src/styles/`。
- 当前桌面应用种子清单在 `backend/app/seed_data/apps.json`。
- 当前前端应用组件映射在 `frontend/src/desktop/app-registry/component-key-map.generated.ts`。
- 当前 `modules/` 目录已存在，含 `ai-assistant/manifest.json` 和 `ai-assistant/sandbox/`。
- 当前 `modules/ai-assistant/manifest.json` 定义了 AI 助手模块占位入口。
- 当前构建管道包含 `scripts/scan-modules.js`，自动扫描 manifest 生成组件映射。
- 当前 `modules/ai-assistant/sandbox/` 是可独立运行的开发环境。
- 当前 `frontend/package.json` 构建脚本已修复为：`scan-modules.js` + `copy-pdf-worker.sh` + `vue-tsc -b` + `vite build`。
- 当前 `vite.config.ts` 已移除旧中文别名和自定义插件，新增 `@modules` 别名指向 `../modules`。
- 当前 `tsconfig.app.json` 路径已更新，移除旧 `后端/应用模块` 引用。
- 当前 `frontend/main.ts` 和 `v-permission.ts` 指令名改为英文。
- 当前所有前端 `@应用模块` 导入已被替换为 platform 原生调用或暂缺处理。
- 当前模块扫描链路已建立：`scripts/scan-modules.js` 扫描 `modules/*/manifest.json`，生成 `component-key-map.generated.ts`。
- 当前 `apps.json` 中 agent 的 `component_key` 已改为英文 `ai-assistant/index.vue`。`component-key-map.ts` 兼容层仍保留旧中文 DB 值映射，避免未重新播种前中断。
- 当前前端构建脚本全部使用英文名称，构建命令链：`scan-modules.js` → `copy-pdf-worker.sh` → `vue-tsc -b` → `vite build`。
- 当前 `frontend/package.json` 中再无中文脚本名和旧 `脚本/` 路径引用。
- 当前 `window-types.ts` 接口已全部改为英文命名。
- 当前 `@应用模块` 导入全部移除。
- 当前 API 类型已修复（~30处中文属性名、语法损坏均已修正）。
- 当前外围 TypeScript 类型已修复：全量 `vue-tsc -b` 通过，0 错误。修复 20 处类型错误，涉及 7 个文件。

## 已修复的 TypeScript 文件

| 文件 | 修复内容 |
|---|---|
| `shared/api/settings.ts` | 修复 `ApiResponse` 未定义、`参数.role`/`参数.username` 属性名不匹配、`项.role`/`项.role矩阵` 属性名不匹配 |
| `shared/components/system-status-panel.vue` | 模板中 `值.状态`→`值.status`、`值.消息`→`值.message` |
| `shared/components/file-format-matrix.vue` | `row.format`→`row.格式`、`attr.category`→`attr.分类`、`attr.description`→`attr.说明` |
| `shared/composables/use-settings-management.ts` | `用户.role`→`用户.角色`、`表单.value.username`→`表单.value.用户名`等 4 处 |
| `shared/composables/use-user-management.ts` | 同上 4 处 |
| `shared/upload/directory-upload.ts` | AxiosResponse 嵌套 `data` 路径修正 |
| `modules/ai-assistant/frontend/index.vue` | `res.success`→`res.data?.success`（3 处 AxiosResponse 类型适配） |

## 待办

- `apps.json` 中剩余 30+ 应用的 `component_key` 仍是中文路径（`应用/xxx/入口.vue`），这些应用暂无新模块载体，保留旧值不影响框架功能。后续模块迁移时同步更新。
- 数据库同步：当前 DB 仍存有旧中文 `component_key`，需在下次 `sync_apps_from_manifest` 运行后更新。

## 当前框架能力

- 登录入口、桌面入口、全局布局。
- 窗口系统、任务栏、启动器、托盘、右侧栏。
- 应用注册、应用打开、窗口承载。
- 共享请求器、响应转换、权限、主题、基础 UI 规范。
- 平台 API、数据库、队列、模型网关、文件存储。

## 当前不属于框架的业务目标

- 知识库业务页面。
- AI 助手业务页面。
- 文件管理业务页面。
- 模块自己的状态、组件、业务流程。

## 目标模块扫描规则

框架只扫描顶层模块清单：

```text
modules/*/manifest.json
```

框架不递归扫描：

```text
modules/*/submodules/*
modules/*/sandbox/*
```

子模块由父模块管理。如果子模块需要出现在桌面启动器里，必须升级为顶层模块。

## 目标模块接入规则

模块接入框架时，必须通过模块 runtime：

```text
modules/{module}/runtime/
modules/{module}/runtime.config.json
```

页面、组件、composables 不直接拼接会随运行环境变化的路径。
