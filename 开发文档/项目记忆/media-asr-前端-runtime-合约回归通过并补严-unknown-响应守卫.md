---
name: "media-asr 前端 runtime 合约回归通过并补严 unknown 响应守卫"
type: "task"
tags: [media-asr, frontend, runtime, typescript, runtime-drift]
agent: "codex-media-asr-worker"
created: "2026-07-03T05:33:09.346584+00:00"
---

本轮作为 Codex media-asr worker 执行前端/runtime 合约回归。验证 `frontend && npm run check:runtime-drift` 通过，`frontend && npx vue-tsc -b --pretty false` 通过，`modules/media-asr/runtime/index.ts` 与 `modules/_template/runtime/index.ts` 完全一致，media-asr 未作为 known variant 登记。审查 `modules/media-asr/frontend/index.vue` 时发现原 `isTranscribeResult` 只校验 segments，未对模板消费的 audio_file_id/text_file_id/text/error/metadata 等字段做完整类型收窄；已在该文件补充 optional number/string/nullable number/metadata 守卫，继续保持 `platform.modules.call` 返回值为 unknown 后显式收窄，无 `any/as any/@ts-ignore/@ts-expect-error`，未使用 `转中文` 改字段。注意：工作区中 `frontend/scripts/check-runtime-drift.js` 与 `modules/media-asr/runtime/index.ts` 已有其他 worker 变更，本 worker 只追加 media-asr frontend 类型守卫。
