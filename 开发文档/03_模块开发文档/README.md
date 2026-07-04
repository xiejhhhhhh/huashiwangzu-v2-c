# 模块开发文档

## 模块目标

模块是桌面里的软件和插件。业务功能优先放入 `modules/`，不要塞进框架。

每个模块必须先在自己的 `sandbox/` 小框架里完成独立开发、运行和验收，再接入主桌面壳。开发态模块和主框架物理隔离；接入态才通过 manifest、runtime 和公开 API 发生交互。

## 当前真实状态

- `modules/_template/` 已创建，包含标准 sandbox 模板、runtime 中间层和最小 `frontend/index.vue` 入口，新模块复制即用。
- `modules/hello-world/` 是第一个跑通端到端接入的最小模块（纯前端），验证了"复制模板→build 扫描→后端 sync→桌面加载→调 runtime SDK"全链路，可作为新模块参考样板。
- **Agent 模块已完整迁移并深度强化**（从 V1 PHP 用 V2 架构重建）：对话 + SSE 流式 + 消息入库、**渐进式工具发现**（3 个元工具 skill_list/skill_describe/skill_use，token 不随模块膨胀）、**engine 子系统**（event-sourcing / budget allocator / compressor / fallback chain / stuck detector / layered memory / experience memory）、**后台任务池**（4 个 registered handler）、**子 Agent 支持**（spawn_subagent）、**治理面板**（per-agent 配置 / 敏感操作审批 / admin dashboard）。
- **知识库已迁入**：完整五层 pipeline（文档注册 → 解析 → 分块向量化 → 页面融合 → 实体图谱+治理），7 个跨模块能力（search/get_block/get_page_fusion/get_entity_dictionary/get_graph_context/get_pending_count/get_evidence_detail）。Agent 经框架能力注册表自动发现，零修改接入。
- 全部模块列表见总索引模块地图，此处不再逐一列出（避免重复）。
- 前端模块扫描链路：`frontend/scripts/scan-modules.js` 扫描 `modules/*/manifest.json`（跳过 `_` 开头目录），生成 `component-key-map.generated.ts`。平台 app 则由 `platform-component-key-map.ts` 用 `import.meta.glob` 自动扫描 `platform/components/apps/*/index.vue`（有组件才有映射，物理上不产生空壳）。
- 后端应用清单同步链路：`backend/app/services/app_service.py` 合并 `backend/app/seed_data/apps.json` 和 `modules/*/manifest.json`，同步到数据库；应用启动时自动 sync，并清理 manifest 中已删除的孤儿 app。
- 平台层已无业务模块代码：`backend/app/services/agent/` 和 `backend/app/services/knowledge/` 已删除。
- 模型网关保留为框架能力：`backend/app/gateway/`，HTTP 层在 `backend/app/routers/gateway.py`（6 端点：models/health/chat/chat-stream/embedding/rerank），含降级链和视觉描述。

## 知识库视频分析专项规划

知识库后续接入视频分析体系时，先按“视频资产 → 时间片段 → ASR/OCR/VLM 证据 → segment content_text → BGE-M3 检索 → 时间点引用”的路径落地，避免一开始把 GraphRAG、视觉向量和复杂对象分割做成前置依赖。详细参考方案见 `knowledge_video_analysis_system_plan.md`，包含参考源码清单、模型选型、表结构、pipeline 分期、检索设计和验收指标。

## 模块数据与交互契约（重要，接模块前必读）

**心智模型**：框架 = 商场（提供水电、电梯、保安等公共设施），模块 = 店铺（自己卖货、自管账本）。公共能力共用框架接口（数量固定、稳定，不随模块增加而膨胀）；业务数据和逻辑全在模块自己里。这是兼容性的根——框架对外接口稳定，模块像装软件一样接入，不用回头改框架。

### 数据归属
- 模块业务表用模块 key 做前缀（如 `oa_*`、`erp_*`、`order_*`、`kb_*`），框架表用 `framework_*`。
- 物理隔离：框架不碰模块表；模块**不直接读写** `framework_*` 表，要框架数据一律走公共 API（runtime SDK）。
- **模块表不加数据库外键**到框架表或其他模块表。跨实体关联只用逻辑编号（如 `owner_id` 存 int、`conversation_id` 存 int），不加 `ForeignKey` 约束；要用户/其他模块的数据走框架鉴权注入或跨模块接口。这样模块表彻底自包含，sandbox 里只建自己的表就能跑，换库/迁移互不牵连。
- 模块自带建表/迁移，跟模块一起进出。**【待定稿】模块自带表的建表/升级标准尚未确定**（当前框架表走 SQLAlchemy `create_all` + Alembic 双轨，见底层文档）。计划在第一个带后端表的模块（Agent 或知识库）落地时定标准、写进 `_template`，之后模块照抄。

### 业务接口归属
- 模块自己的业务接口**全部**写在 `modules/{key}/backend/router.py`，manifest 声明 `backend.router`，框架启动自动扫描挂载（`registry.py`），**加模块不改框架代码**。
- 只有"所有模块都需要的新公共能力"才往框架加接口——慎重，因为框架接口是契约，要长期稳定。

### 跨模块调用（必须 100% 经框架，禁止跳过）
模块间交互（如 Agent 调知识库检索、Agent 调 ERP 数据）必须经框架统一通路，**禁止互相 import 代码、禁止直接读对方的表**。现状：
- **前端跨模块（已有，G12 已交付）**：底層引擎 `desktop/app-registry/desktop-app-handle-v2.ts` 提供 `sendCommand(目标模块, 动作, 参数)`、`requestData(目标模块, 数据类型, 过滤)`；目标模块用 `registerActionHandler` 声明对外开放的动作，未声明的调不到（`ERR_ACTION_NOT_PUBLIC`）；含权限校验 + 审计 + 超时。**runtime SDK 已封装为 `platform.modules.call(targetModule, action, parameters)` + `platform.modules.capabilities()`**，模块可直接调用。
- **后端跨模块（已有，G12 已交付）**：`backend/app/services/module_registry.py`（`register_capability` + `call_capability`） + `/api/modules/call` + `/api/modules/capabilities`。进程内调用经框架统一入口，运行时以 `register_capability(module, action, handler)` 注册为准；未注册的能力调不到。manifest 的 `public_actions` 字段当前作为模块对外能力声明元数据同步到应用注册表。

### 文件存储 / 去重（契约已就绪）
模块上传文件统一走框架文件接口。框架内容寻址去重：相同内容（md5 相同）只存一份物理文件、多条记录共享 `storage_path`；永久删除时统计同 md5 的未删除记录数，归零才删物理文件（复制也复用同一物理文件，不破坏去重）。模块无需关心去重，调框架文件接口即可，存储空间由框架保持干净。

## 终端/CLI 与执行类工具的边界（已决策，勿再质疑用 Docker）

Agent 的终端工具（`terminal-tools`）让 Agent 能跑命令/写脚本，是"通用兜底能力"。其安全边界是**权衡后的明确选择，新会话不要再提"要不要 Docker 强隔离"**：

- **本地执行，不用 Docker**（Docker 重复装环境、占资源、拉起慢，不划算）。
- **行为边界**：命令 cwd 锁死用户工作区 `data/workspaces/{user_id}/`、文件路径约束在工作区内（越界绝对路径/`../`/`~` 拒绝）、危险命令（`sudo`/`rm -rf /`/越界）拦截、执行超时 + 输出上限、联网允许（局域网内部）。
- **两套世界分离**（关键）：桌面/文件感知走 `desktop-tools`（查框架文件系统，**非宿主机桌面**）；命令执行走 `terminal-tools`（工作区，**非宿主机其他路径**）。CLI 绝不指向宿主机真实桌面/文件，从根上杜绝"读桌面读成宿主机、存文件操控宿主机"。
- **产物**：工作区是草稿（不上桌面），成果由 Agent 显式 `publish` 进框架文件系统才上桌面；未交付的临时文件按会话结束/超时/超大小自动清。
- 隔离强度 = 应用层约束 + 局域网信任同事（够用）；非 Docker 级强隔离是明确取舍，不是遗漏。详见 `开发文档/01_框架开发文档/README.md` C22、`AGENTS.md` 规则 21。

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

### sandbox 验收矩阵

每个模块的 README 必须写清“可复现”的验收命令，不能只写“跑过 sandbox”。

| 模块形态 | 必填验收 |
|----------|----------|
| 纯前端模块 | `cd modules/{key}/sandbox && npm install && npm run build`，再跑 `cd frontend && npm run build` |
| 有后端能力模块 | 后端能力测试 + sandbox 前端 build + 主框架 build |
| 文件解析模块 | `sandbox/test_module.py` 必须使用真实样例文件验证 blocks/resources，不只 import 成功 |
| 依赖框架后端的 sandbox | 命令必须显式使用 `backend/.venv/bin/python` 和必要的 `PYTHONPATH=backend`，不得写成裸 `python3` |
| 需要登录态/生产库的模块 | README 必须说明使用主框架活栈验证，不能把 sandbox 登录壳结果当主框架验收 |

当前 `smoke_all` 只能证明主框架 happy path，不等于每个模块 sandbox 都通过。发布前应维护一张模块验收矩阵：模块 key、sandbox 命令、主框架命令、是否清理测试数据、最近一次结果。

### Parser / Content IR 验收矩阵

文件解析模块输出必须逐步收口到统一 Content IR。当前最低契约：

| 字段 | 要求 |
|---|---|
| `file_id` | 原框架文件 ID |
| `format` | 小写扩展名或解析格式 |
| `blocks` | 内容块数组，`type` 使用英文 Content IR block type：`heading/paragraph/table/sheet/range/slide/image/chart/code/quote/divider` |
| `resources` | 二进制或嵌入资源引用数组，可为空 |
| `metadata` | 解析器、截断、质量、警告等结构化元数据；长正文不得塞 manifest |
| `warnings` | 可恢复问题列表；失败不能包装成假成功 |

Parser README 的 `Acceptance Matrix` 之外，还应声明：支持扩展名、capability 名称、返回 block types、是否返回 resources、sandbox 样例命令和 skip 原因。ContentPackage 状态机按框架口径解释：

```text
draft_package -> parsed_package/degraded/failed -> compiled_preview -> published_artifact/file -> archived
```

历史兼容说明：部分旧 parser 仍会通过 legacy `{blocks, resources}` 进入 ContentPackage pipeline；新增或修改 parser 时必须优先输出英文 block type，并通过 sandbox 样例验证 Content IR 兼容性。

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
