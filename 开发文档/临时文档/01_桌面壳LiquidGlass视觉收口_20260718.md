# 桌面壳 Liquid Glass 视觉收口（历史完成索引）

> 日期：2026-07-18
> 状态：**V1 + V2 + V3 已完成；后续一致性施工见 04**
> 对标 A：[macOS 27](https://macos27.kimi.page/)
> 对标 B：[macOS 28 fevze](https://macbook.fevze.com/)（后补对照）
> 基线：`http://127.0.0.1:5173/desktop`

## 0. 结论

本文件记录 **V1–V3 已落地能力**。
**尚未统一的“多配方/几何/真壁纸/业务 chrome 覆盖”** 已蒸馏到：

`开发文档/临时文档/04_桌面壳统一一致性收口方案_双Demo对照_20260718.md`

后续不要在本文件继续开新施工项。

## 1. 已落地能力

### V1
- Glass primitive 类与 token
- 复杂壁纸（SVG）
- refraction 节点与部分接线
- 窗口 inactive 灰灯 + hover 符号
- Dock 邻居放大曲线

### V2
- 通知中心外壳 mac 化（业务数据保留）
- Control Center 最小版
- 桌面 toast/dialog 去 Element
- Menubar solid-on-touch
- Launchpad 假分页清理

### V3
- 图标分层材质 V2
- minimize genie 近似 + Dock bounce
- App Switcher + `window.__HSWZ_DESKTOP_SHELL__`
- `app-window-frame` / toolbar glass；Office / 知识库入口头

### 验证（历史）
`desktop-macos-shell` + `desktop-notification-center` = 14 passed

## 2. 关键路径

- `frontend/src/desktop/design-system/desktop-design-tokens.css`
- `frontend/src/styles/desktop-shell.css`
- `frontend/src/desktop/**`
- `frontend/tests/desktop-macos-shell.spec.mjs`
- `frontend/tests/desktop-notification-center.spec.mjs`

## 3. 下一跳

只跟：**04_桌面壳统一一致性收口方案_双Demo对照_20260718.md**
