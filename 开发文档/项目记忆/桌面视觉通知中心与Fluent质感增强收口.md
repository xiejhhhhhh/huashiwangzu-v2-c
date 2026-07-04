# 桌面视觉通知中心与 Fluent 质感增强收口

## 任务

执行 `执行信-桌面视觉通知中心与Fluent质感增强.md`，只做桌面视觉体验增强，不改业务 API 契约。

## 改动

- `frontend/src/shared/components/notification-panel.vue`
  - 通知中心增加 `dialog`/`aria-labelledby`/`aria-busy`，错误、加载、空态和反馈分组更清晰。
  - 将 action item 按主反馈、任务、Agent、Knowledge 分层展示。
  - 未读通知的“标为已读”从可点击 `span` 改为可键盘访问的 `button`。
  - 增加 Fluent 风格卡片、左侧状态条、阴影、hover、focus-visible 和 loading pulse。
- `frontend/src/desktop/taskbar/taskbar-notifications.vue`
  - 通知按钮增加 `aria-expanded`/`aria-controls`。
  - 打开面板后聚焦面板，`Escape` 关闭并把焦点回到铃铛按钮。
  - 状态增加非颜色提示点、hover/focus 反馈。
  - 通知面板宽度改为响应式，增加玻璃感、圆角和层级阴影。
- `frontend/src/desktop/taskbar/desktop-taskbar.vue`
  - 开始按钮和窗口项补 `role/button/tabindex/keydown`。
  - 活跃/最小化窗口增加底部状态条和焦点态。
- `frontend/src/shared/components/load-state-banner.vue`
  - 错误/陈旧横幅视觉与通知中心对齐，补 `alert/status` 语义和 hover/focus 动效。
- `frontend/src/styles/desktop-shell.css`
  - 桌面 hint、错误态、加载态、拖拽态和窗口 active/inactive 层级增强。
- `frontend/tests/desktop-notification-center.spec.mjs`
  - 新增 mock 级 Playwright 测试，覆盖通知中心打开、分组可见、阴影/圆角、未读通知标为已读，以及键盘打开/Escape 关闭焦点回收。

## 验证

```bash
cd frontend && npm run build
cd frontend && PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/desktop-notification-center.spec.mjs --project=admin
rg -n "\bany\b|as any|@ts-ignore|@ts-expect-error" frontend/src/desktop/taskbar frontend/src/shared/components/notification-panel.vue frontend/src/shared/components/load-state-banner.vue frontend/src/desktop/shell frontend/src/styles frontend/tests/desktop-notification-center.spec.mjs
git diff --check -- frontend/src/desktop/taskbar/desktop-taskbar.vue frontend/src/desktop/taskbar/taskbar-notifications.vue frontend/src/shared/components/notification-panel.vue frontend/src/shared/components/load-state-banner.vue frontend/src/styles/desktop-shell.css frontend/tests/desktop-notification-center.spec.mjs
```

结果：

- `npm run build` 通过。
- `PLAYWRIGHT_EXTERNAL_SERVER=1 npx playwright test tests/desktop-notification-center.spec.mjs --project=admin` 3/3 通过。
- 类型压制扫描无命中。
- `git diff --check` 无空白错误。

2026-07-04 主会话复验：上述四项重新执行通过；5173 活栈可访问，通知中心最小 Playwright 仍为 3/3 通过。

## 边界说明

本次视觉任务实际改动限定在执行信允许范围内：

- `frontend/src/desktop/taskbar/desktop-taskbar.vue`
- `frontend/src/desktop/taskbar/taskbar-notifications.vue`
- `frontend/src/shared/components/load-state-banner.vue`
- `frontend/src/shared/components/notification-panel.vue`
- `frontend/src/styles/desktop-shell.css`
- `frontend/tests/desktop-notification-center.spec.mjs`
- 本收口文档

收口时工作区还存在其他并行任务留下的 dirty/untracked 文件（如后端、Agent、窗口 snap、ContentPackage 文档等），不属于本任务产物，未做修改或回退。
