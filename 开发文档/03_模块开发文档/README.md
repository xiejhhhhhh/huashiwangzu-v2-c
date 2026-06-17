# 模块开发文档

## 模块目标

模块是桌面里的软件和插件。业务功能优先放入 `modules/`，不要塞进框架。

每个模块必须先在自己的 `sandbox/` 小框架里完成独立开发、运行和验收，再接入主桌面壳。开发态模块和主框架物理隔离；接入态才通过 manifest、runtime 和公开 API 发生交互。

## 当前真实状态

- `modules/_template/` 已创建，包含标准 sandbox 模板、runtime 中间层和最小 `frontend/index.vue` 入口，新模块复制即用。
- 当前没有已接入的业务模块；`modules/` 只保留 `_template/`，后续业务模块按模板重新创建。
- 前端模块扫描链路：`frontend/scripts/scan-modules.js` 扫描 `modules/*/manifest.json`（跳过 `_` 开头目录），生成 `component-key-map.generated.ts`。
- 后端应用清单同步链路：`backend/app/services/app_service.py` 合并 `backend/app/seed_data/apps.json` 和 `modules/*/manifest.json`，把平台应用与顶层模块应用一起同步到数据库。
- 平台层已无业务模块代码：`backend/app/services/agent/` 和 `backend/app/services/knowledge/` 已删除，对应的 18 个 router 已移除。
- 模型网关保留为框架能力：`backend/app/gateway/`（原 `services/agent/gateway/`）。

## 新建模块流程

```bash
# 1. 复制模板
cp -r modules/_template modules/YOUR_MODULE_KEY

# 2. 替换占位符
#    MODULE_KEY          → your-module-key
#    MODULE_DISPLAY_NAME → Your Module Display Name
#    sandbox 端口通过 VITE_SANDBOX_PORT 或 sandbox/vite.config.ts 设置

# 3. 开发
cd modules/YOUR_MODULE_KEY/sandbox
npm install
npm run dev

# 4. 集成验证
cd /path/to/frontend
npm run build
```

## 目标模块结构

```text
modules/{module_name}/
  manifest.json          ← 模块身份（名称、图标、权限、窗口规格、后端路由）
  frontend/              ← Vue 组件和业务逻辑
    index.vue            ← 入口组件
  backend/               ← (可选) Python FastAPI router
    router.py            ← export router = APIRouter(...)
  runtime/               ← 运行时中间层（从 _template 复制）
    index.ts             ← getApiUrl(), hasPermission(), getModuleSetting(), initRuntime()
  sandbox/               ← 独立开发环境
    package.json
    vite.config.ts
    runtime.config.json
    index.html
    src/main.ts
    src/App.vue
  submodules/            ← (可选) 子模块
  test-data/             ← 测试数据（有来源、有标记、有清理）
  assets/                ← 静态资源
  module-docs/           ← 模块文档
  tests/                 ← 模块级测试
```

## 目标 sandbox 门禁

模块开发必须先完成 sandbox 自测，再接入主框架。

```text
modules/{module_name}/sandbox/
  index.html
  vite.config.ts
  runtime.config.json
  package.json
  src/main.ts
  src/App.vue
```

未通过 sandbox 的模块，不允许接入桌面壳。

### sandbox 模板不够用时

sandbox 是模块开发态的小框架。如果模块需要更多能力：

1. 优先在模块自己的 `runtime/` 中补齐适配层。
2. 在 sandbox 中提供 mock、stub 或模块本地测试组件。
3. 在 `sandbox/package.json` 中添加模块开发需要的独立依赖。
4. 不允许从 `frontend/src/` 复制框架内部代码到模块或 sandbox；确实需要成为公共能力时，先把能力抽象成明确的平台公开 API 或模块 runtime 契约。

## 图标（Icon）

模块图标由模块自己提供，框架只负责引用加载。**禁止将模块图标放入框架目录。**

### 两种图标方式

| 方式 | manifest 字段 | 说明 |
|------|--------------|------|
| SVG 图标 | `icon` | Element Plus / Fluent UI 图标 key，框架内置 SVG 映射。零额外文件 |
| 自定义 PNG | `icon_asset` | 模块自己的 PNG 文件，放在模块目录内，构建时自动注册 |

### 使用 SVG 图标（推荐，零成本）

只需在 manifest 里指定 `icon` 为框架支持的 key：

```json
{
  "icon": "ChatDotRound"
}
```

框架内置了常用图标的 SVG 映射（`app-icon-assets.ts` 的 `svgMap`）。支持的 key：`Files`, `Delete`, `Collection`, `ChatDotRound`, `Setting`, `List`, `Dashboard`, `View`, `EditPen`, `Grid`, `DocumentCopy`, `Document`, `DataBoard`。未匹配的 key 兜底为文件夹图标。

### 使用自定义 PNG 图标

当 SVG 图标不满足需求时，模块可以提供自己的 PNG：

**1. 放置图标文件：**

```text
modules/{module_name}/frontend/assets/icon.png
```

**2. 在 manifest 声明：**

```json
{
  "icon": "ChatDotRound",
  "icon_asset": "assets/icon.png"
}
```

- `icon` — 仍然是必填的，作为 SVG 兜底（PNG 加载失败时使用）
- `icon_asset` — 可选，相对 `frontend/` 的路径。留空则只使用 SVG

**3. 构建时自动注册：**

`scripts/scan-modules.js` 扫描 manifest 中的 `icon_asset`，生成 `module-icon-assets.generated.ts`。框架的 `app-icon-assets.ts` 会自动 merge 模块图标到 `imageMap`，无需手动改框架代码。

### 禁止事项

- ❌ **禁止**将模块 PNG 图标放入 `frontend/src/assets/desktop-icons/`——那是框架图标目录
- ❌ **禁止**在 `app-icon-assets.ts` 中硬编码模块图标的 import 和映射
- ✅ 模块图标只能通过 manifest 的 `icon_asset` 声明，放在 `modules/{name}/frontend/` 下

## 模块间协作

多个模块可以同时独立开发——每个 sandbox 是独立 Vite 项目，有自己的端口，通过 proxy 连到同一个后端。互不依赖、互不干扰。

## 子模块规则

复杂模块可以拆子模块：

```text
modules/knowledge/submodules/catalog/
modules/knowledge/submodules/ingestion/
modules/knowledge/submodules/retrieval/
modules/knowledge/submodules/qa/
```

子模块由父模块扫描和管理，不进入桌面壳全局扫描。子模块要成为桌面应用，必须升级为顶层模块。

## Runtime 中间层

每个模块的 `runtime/index.ts` 提供：

- `getApiUrl(path)` — 构建完整 API URL
- `hasPermission(permission)` — 权限检查
- `getModuleSetting(key)` — 读取模块配置
- `getMode()` — sandbox / framework 模式

模块业务代码只通过 runtime 获取这些值，不硬编码路径。sandbox 模式读 `runtime.config.json`，framework 模式由桌面壳注入。

## 框架边界

开发态模块和主框架必须物理隔离。模块在自己的 `sandbox/` 小框架中运行，模块前端不导入 `@/`，模块后端不写入 `backend/app`，模块测试数据也留在模块边界内。

接入态才允许按契约交互。模块可以调用平台公开能力，例如 HTTP API、权限、文件、队列、数据库服务入口和模型网关；这些调用必须经由模块 `runtime/`、模块后端 router 或 manifest 声明完成。

禁止事项：

- 模块前端不得导入 `@/` 下的框架内部文件。
- 模块业务类型不得放入 `frontend/src/shared/api/common-data-types.ts` 等框架共享类型文件。
- 模块后端 router 不得手写加入 `PLATFORM_ROUTER_MODULES`，只能由 manifest 的 `backend.router` 声明动态挂载。
- 模块业务应用不得写入 `backend/app/seed_data/apps.json`，只能写入模块自己的 `manifest.json`。
- 模块 sandbox 不得把主框架代码复制进来当依赖；需要框架能力时使用 mock、runtime 适配或新增平台公开 API。

## 测试数据规则

- 有来源。
- 有标记。
- 有清理脚本。
- 用完清空。

## 文档规则

每个模块目录只保留一个长期 `README.md`。临时方案完成后必须合并回该模块 `README.md`，然后删除临时文档。
