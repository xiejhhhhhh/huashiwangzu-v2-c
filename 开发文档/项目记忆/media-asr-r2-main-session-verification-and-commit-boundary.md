---
name: "media-asr r2 main-session verification and commit boundary"
type: "task"
tags: [media-asr, r2, verification, main-session, ffprobe, model-boundary]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T08:26:24.140876+00:00"
---

# 改了什么

主会话接管并验收 media-asr 子代理产物：能力入口在进入文件读取/ffmpeg/模型下载前校验 file_id、folder_id、sample_rate、audio_format、Whisper model 与 language；音视频探测收口到 ffprobe/Python helper；sandbox 覆盖生产 router/service 边界。

# 验证了什么

- CodeGraph impact: `modules/media-asr/backend/router.py` 与 `modules/media-asr/backend/services/audio_service.py` 影响面均限本模块。
- `lint`: router/audio_service/sandbox all passed。
- `run_test`: `modules/media-asr/sandbox/test_module.py` 4 passed。
- 活栈：`GET /api/health` 200 且 module_errors=null；`GET /api/media-asr/health` 200。
- 活栈坏参：`media-asr:extract_audio {file_id:0}` 422；`media-asr:transcribe_audio {file_id:1, model:"remote/huge"}` 422；`POST /api/media-asr/transcribe-video` 非法 sample_rate 422。
- backend tail_log 无新增错误输出。

# 是否还有残留风险

工作区同时存在 douyin-delivery/office-gen/scheduler 中断半成品和历史 data/uploads 未跟踪文件；本次只 stage/commit media-asr 及其项目记忆，后续逐块主会话复核。

# 关联 commit

待提交：`harden media asr boundaries r2`。
