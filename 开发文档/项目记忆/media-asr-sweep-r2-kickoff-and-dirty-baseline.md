---
name: "media-asr sweep r2 kickoff and dirty baseline"
type: "task"
tags: [media-asr, r2, sweep, boundary, kickoff]
agent: "codex-media-asr-sweep-20260703-r2"
created: "2026-07-03T08:00:59.746967+00:00"
---

2026-07-03 开工 modules/media-asr r2 扫雷。已按流程调用 brief、plan_task(module_key='media-asr')、worktree_guard(include_untracked=true)。当前工作区存在其他并行 agent 改动：email-parser/image-vision/markdown-parser/structured-parser、data/uploads 以及相关项目记忆；media-asr 暂未在 dirty 列表中。边界：只允许修改 modules/media-asr/ 与本 agent 项目记忆，不碰 backend/app、frontend/src、其他 modules、data/uploads。重点检查 file_id 权限统一通路、坏 file_id/格式结构化 4xx、假成功、本地轻量前处理与昂贵模型调用边界、sandbox 是否测生产代码、manifest/capability 一致性。
