---
name: "media-asr sweep r2 validation and sandbox fixes completed"
type: "task"
tags: [media-asr, r2, validation, ffprobe, model-boundary, sandbox, verification]
agent: "codex-media-asr-sweep-20260703-r2"
created: "2026-07-03T08:07:41.790222+00:00"
---

完成 modules/media-asr r2 扫雷修复。改动仅限 media-asr 产品文件：README.md、backend/router.py、backend/services/audio_service.py、manifest.json、sandbox/test_module.py；另写本 agent 项目记忆。修复内容：capability 入口新增 file_id/sample_rate/folder_id 结构化 ValidationError，避免裸 ValueError/500；Whisper model 加白名单 tiny/small/medium/large/large-v2/large-v3/turbo，未知模型在文件读取和 ASR 前 422 拦截；audio_service 新增 ffprobe 本地媒体探测，校验可读性、音轨/视频流类型、duration、4 小时时长上限，ffmpeg 空输出不再假成功；transcribe 结果缺 text/segments 时不假成功；manifest/register_capability/README 对模型说明同步；sandbox 改为导入生产 router/service，stub DB/media/model 边界，验证 manifest 与运行时注册一致、生产 validator、坏参数在 file runner 前失败、extract_audio 返回契约。验证：ruff 三个 Python 文件通过；直接运行 backend/.venv/bin/python modules/media-asr/sandbox/test_module.py 通过；run_test pytest 4 passed；/api/health ok；live call_capability media-asr:extract_audio {file_id:0} 返回 422 file_id must be positive；live call_capability media-asr:transcribe_audio {file_id:1, model:remote/huge} 返回 422 model must be one of...。finish_task 因全仓存在其他并行 agent 改动和 data/uploads dirty 判 false，但 media-asr 本次产品改动文件仅 5 个，未触碰 backend/app、frontend/src、其他 modules 或 data/uploads。关联 commit：未提交。
