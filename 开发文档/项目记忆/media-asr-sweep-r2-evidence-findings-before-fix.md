---
name: "media-asr sweep r2 evidence findings before fix"
type: "task"
tags: [media-asr, r2, evidence, file_id, validation, sandbox, model-boundary]
agent: "codex-media-asr-sweep-20260703-r2"
created: "2026-07-03T08:02:38.471410+00:00"
---

证据阶段完成：routes/capabilities/db_schema/code_explore/code_node/code_impact 均已调用。media-asr file_id 主链路经 run_uploaded_file_capability -> read_uploaded_file -> check_file_access，权限通路正确。发现待修问题：capability 参数中 file_id/sample_rate/folder_id 使用裸 int 可能抛 ValueError 形成非结构化 500；model 未白名单限制，任意字符串可能触发 mlx_whisper 下载/昂贵调用；ASR/抽音频前缺轻量 ffprobe 媒体探测、音轨/时长边界和空输出检查；sandbox/test_module.py 未导入生产 router/service，仅手写参数和返回 shape 且字段与真实返回漂移；manifest/capability 对 Whisper 支持模型说明不完全一致。计划只改 modules/media-asr/ 下 router.py、audio_service.py、manifest.json、README.md、sandbox/test_module.py。
