# mac-app-v1 App UI Kit

桌面内运行的软件统一脸。后端只提供数据与 capability；前端用本 kit 组布局。

更完整的框架合同：`开发文档/01_框架开发文档/README.md` §1.1。

## 最小用法

```vue
<script setup lang="ts">
import { MacAppShell, MacEmptyState, useAppFeedback } from '@/desktop/app-kit'

const { success } = useAppFeedback()
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

## 规则

1. 新 Product 声明 `uiContract.kit = "mac-app-v1"` + `layout`（`scan-products` 门禁）
2. 反馈用 `useAppFeedback()`，不要 `ElMessage`
3. 不要在业务页写第三套灰白后台皮肤
4. 快捷键默认不抢浏览器键（见 desktopConfig.enableDesktopHotkeys）
5. 后端禁止下发颜色/CSS/组件名当业务逻辑

## layout

`finder | document | chat | settings | dashboard | utility`

## 门禁

- 构建：`node frontend/scripts/scan-products.js`（缺 uiContract fail）
- 运行时 DEV：`app-loader.validateProductUiContract` 控制台告警
- Catalog：`GET /api/desktop/products` 透传 `uiContract`
