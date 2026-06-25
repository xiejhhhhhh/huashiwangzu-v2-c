### 桌面壳进阶交互调研-Windows对标与开源学习（2026-06-25）
- 做了什么：对照 Windows 11 交互 + VS Code CommandsRegistry、Fluent 2 Motion 等开源项目调研桌面壳 5 个交互维度，出调研报告
- 关键发现：(1) 通知后端已就绪前端只缺 UI 组件 (2) 窗口无任何边缘磁吸（代码中的 "snap" 全是 session snapshot/图标吸附）(3) app-level action-registry 存在但缺少系统级 CommandRegistry (4) 动效 CSS 只有 duration+ease，缺 Fluent 2 级 cubic-bezier 曲线分类
- 推荐先做 3 件事：CommandRegistry > 窗口磁吸 > 通知中心前端组件
- 关联 commit：未改代码，无 commit
- agent: research
