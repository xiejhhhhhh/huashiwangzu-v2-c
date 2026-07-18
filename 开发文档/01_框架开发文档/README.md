# 框架开发文档

框架能力在 `frontend/src/` 与 `backend/app/`。业务模块只走 Product / capability，不直接改壳层。

## 1. 前端分层

```text
frontend/src/
├── app-entry/          路由与应用入口
├── desktop/            桌面壳（菜单栏/Dock/窗口/启动器/Spotlight/图标网格）
├── product-runtime/    产品目录缓存与组件映射
├── platform-sdk/       平台 API 聚合出口
├── workspace-runtime/  工作区会话辅助
├── platform/           登录与用户态
└── shared/             通用 API、类型、组合式函数
```

技术栈：Vue 3 + TypeScript + Vite。壳层 UI 以 macOS 语义为主。

### 1.1 应用 UI 契约（`mac-app-v1`）——怎么用

桌面内软件统一脸。**后端只出数据/capability；脸必须来自 kit。**

```vue
<script setup lang="ts">
import { MacAppShell, MacEmptyState, useAppFeedback } from '@/desktop/app-kit'
const { success, error } = useAppFeedback()
</script>

<template>
  <MacAppShell layout="finder">
    <template #toolbar>工具条</template>
    <template #sidebar>侧栏</template>
    <MacEmptyState title="没有项目" description="从菜单新建或导入。" />
    <template #statusbar>0 项</template>
  </MacAppShell>
</template>
```

| 规则 | 说明 |
|------|------|
| 目录 | `frontend/src/desktop/app-kit/`（`MacAppShell` / `MacEmptyState` / `useAppFeedback` / tokens） |
| layout | `finder \| document \| chat \| settings \| dashboard \| utility` |
| 反馈 | `useAppFeedback()` → `desktopMessage`；**禁止**业务页 `ElMessage` 当系统提示 |
| Element | 复杂表格等可继续用 EP **控件**；容器/侧栏/工具条/空态必须 kit |
| 快捷键 | `desktopConfig.enableDesktopHotkeys` **默认 false**；功能以菜单与按钮为主 |
| Product 声明 | `products/*/product.json` 必填 `uiContract.kit = "mac-app-v1"` + `layout` |
| 门禁 | `node frontend/scripts/scan-products.js` 缺契约 fail build；`app-loader` DEV 告警 |

`product.json` 示例：

```json
"uiContract": {
  "kit": "mac-app-v1",
  "layout": "finder",
  "shell": { "useAppWindowFrame": true, "sidebar": "required", "toolbar": "required", "statusbar": "optional" },
  "feedback": "desktop-kit",
  "density": "comfortable"
}
```

已对齐主路径：files / office / knowledge / ai / settings / recycle（及全量 10 产品声明）。
施工归档：`开发文档/临时文档/05_mac应用UI契约与软件风格统一施工方案_20260718.md`（切片 1–6 完成；Win11 完整壳仍另立）。

## 2. 桌面壳（macOS Shell）

入口：`/desktop` → `frontend/src/desktop/shell/index.vue`

### 2.1 职责划分

| 区域 | 职责 | 关键文件 |
|------|------|----------|
| MenuBar | 当前应用菜单、系统状态、通知入口、账户、时钟 | `desktop/menubar/desktop-menu-bar.vue` |
| Dock | 启动/激活应用、运行点、进度、应用右键窗口列表 | `desktop/taskbar/desktop-taskbar.vue` |
| WindowFrame | 交通灯、标题栏、拖拽缩放、最小化动画 | `desktop/window-manager/desktop-window-frame.vue` |
| Launchpad | 全屏浏览/启动全部应用 | `desktop/launcher/desktop-launcher.vue` |
| Spotlight | 搜索应用/文件/命令 | `desktop/launcher/desktop-spotlight.vue` |
| Desktop Icons | 文件/应用图标、选择、右键、拖放 | `desktop/shell/desktop-icon-grid.vue` |

### 2.2 皮肤、几何与材质 token

桌面是 **一套行为运行时 + 可切换视觉皮肤**（不是两套前端工程）。

| 皮肤 | 说明 |
|------|------|
| `macos`（默认） | Liquid Glass 一致性配方 |
| `win11` | 插槽已就绪（metrics + mica 起步 token；完整 Win11 chrome 待补） |

```ts
// 运行时
window.__HSWZ_DESKTOP_SHELL__.setShellSkin('macos' | 'win11')
window.__HSWZ_DESKTOP_SHELL__.listShellSkins()

// 配置
useDesktopConfig().setShellSkin('win11')
```

代码位置：

- 皮肤合同：`frontend/src/desktop/skins/*`
- 偏好：`config/desktop-preferences.ts`（`shellSkin`）
- 几何：`config/desktop-chrome-metrics.ts`（读 active skin）
- 默认 token：`design-system/desktop-design-tokens.css`
- 材质 primitive：`styles/desktop-shell.css`（`.glass-*`）

mac 默认合同（**已收完**）：

- 菜单栏高 `28px`
- Dock 高 `66px`，底边距 `12px`，圆角 `18px`
- 标题栏高 `44px`，窗口圆角 `14px`
- 主配方：`blur(34px) saturate(182%)` 族变量 `--desktop-lg-*`
- 默认壁纸：`/desktop/wallpaper-macos-default.svg`
- 系统面板与业务入口 chrome 已并入同一材质家族

Win11：仅 skin 插槽；完整 chrome 另立阶段。

详细：

- 壳层/皮肤：`开发文档/临时文档/04_桌面壳统一一致性收口方案_双Demo对照_20260718.md`
- 应用 UI 契约（**已完成**，用法见上文 §1.1）：`开发文档/临时文档/05_mac应用UI契约与软件风格统一施工方案_20260718.md`

### 2.3 窗口与会话

- 管理器：`desktop/window-manager/window-manager.ts`
- 状态持久化：`desktop-state-store.ts`（`expected_version` CAS，冲突 409 后重载）
- 会话恢复：`desktop-session-restore.ts`
- 支持普通/最大化/最小化、多实例、payload、贴靠预览

### 2.4 应用/产品加载（正式单路径）

桌面只消费 Product Catalog：

```text
GET /api/desktop/products
  → app-loader.ts
  → 桌面图标 / Dock / Launchpad
```

打开文件只走 Content Open Resolver：

```text
POST /api/content/open
  → app-opener / content-file-opener
  → 打开对应 Product 窗口
```

关键文件：

- `desktop/app-registry/app-loader.ts`
- `desktop/app-registry/app-opener.ts`
- `desktop/app-registry/content-file-opener.ts`
- `shared/api/products.ts`
- `shared/api/content-runtime.ts`
- `product-runtime/*`（`scripts/scan-products.js` 生成组件映射）

产品声明：`products/{id}/product.json`（**必填** `uiContract.kit=mac-app-v1` + `layout`）
前端组件映射：构建时 `node frontend/scripts/scan-products.js` 生成 `@products` loader，并校验 uiContract。
Catalog API 透传 `uiContract`（`product_catalog_service`），不解析样式。

首批 Product：`files / office / text / media / knowledge / ai / messages / content-studio / settings / recycle`。

### 2.5 图标

- `desktop/components/app-icon.vue`
- `desktop/components/app-icon-catalog.ts`
- 当前为圆角渐变 + 线稿 V1；对象级图标 V2 未落地。

## 3. 产品与内容运行时（平台合同）

### 3.1 Product Catalog

| 调用 | 说明 |
|------|------|
| `GET /api/desktop/products` | 有效产品清单（按 sortOrder） |
| `GET /api/desktop/products/{id}` | 单个产品 |

服务：`backend/app/services/product_catalog_service.py`
路由：`backend/app/routers/products.py`

### 3.2 Content Open / Runtime

| 调用 | 说明 |
|------|------|
| `POST /api/content/open` | 统一打开决议（唯一打开入口） |
| `POST /api/content/drafts` | 新建草稿 Package |
| `GET /api/content/packages/{id}/hydrate` | 读取可编辑会话 |
| `POST /api/content/packages/{id}/save` | 保存（`expectedVersionId` CAS） |
| `POST /api/content/packages/{id}/save-as` | 另存（File 物化可能 deferred） |
| `POST /api/content/packages/{id}/export` | 导出 |
| `POST /api/content/packages/{id}/publish` | 发布 |
| `POST /api/content/packages/{id}/locks` | 编辑租约 |
| `POST /api/content/packages/{id}/locks/renew` | 续租 |

服务：

- `content_open_resolver.py`
- `services/content/content_runtime_service.py`
- `services/content/canonical_normalizer.py`
- `services/content/ingestion_*`
- `services/content_runtime_schema.py`（启动幂等补 schema）

契约：`backend/app/contracts/canonical_content_ir.py` 等。

原则：

- 读：canonical 优先，缺失则现场归一 `content_json`
- 写：draft / save / lease 走 Runtime
- 上传只唤醒异步摄取 DAG；模型预算不足阶段标 `deferred/skipped`，不假绿

### 3.3 前端 SDK

- `frontend/src/platform-sdk/index.ts`：products / content 等聚合导出
- `frontend/src/product-runtime/index.ts`：catalog 缓存
- `frontend/src/workspace-runtime/index.ts`：工作区辅助

## 4. 模块加载

1. 构建扫描 `modules/*/manifest.json`（及 `products/*/product.json`）
2. 生成组件注册表
3. 桌面按 Product 可见性/权限加载
4. 业务入口：`modules/{key}/frontend/index.vue` 或 `products/{id}/frontend/index.vue`

## 5. 改动边界

- 壳层 / 窗口 / 产品运行时：只动 `frontend/src/`、`backend/app/`、`products/`
- 业务模块：只动 `modules/{key}/`
- 跨模块：capability bus / `/api/modules/call`
