---
name: "media-intelligence r2 分层流水线骨架与契约落地完成"
type: "task"
tags: [media-intelligence, r2, architecture, provider-registry, sandbox, task]
agent: "codex-media-intelligence-architecture-20260703-r2"
created: "2026-07-03T07:29:36.699157+00:00"
---

# 改了什么

新增 `modules/media-intelligence/` 模块，围绕“本地算法 -> 小模型 provider -> VLM refine”的分层媒体智能流水线落地可维护骨架，不引入重依赖、不训练模型。

核心文件：
- `manifest.json`：声明 8 个 public_actions：analyze_image/analyze_video/extract_keyframes/ocr/embed_image/detect_objects/summarize_media/vlm_refine。
- `backend/providers/`：新增 base、local_algorithms、small_model、vlm、registry，当前均为确定性 placeholder/provider registry。
- `backend/pipeline.py`：统一输出 `media-intelligence.analysis.v1`，含 source/stages/signals/artifacts/summary/tags/confidence/warnings/providers。
- `backend/router.py`：HTTP + capability 注册；文件型能力走 `run_uploaded_file_capability`，由框架统一校验文件访问。
- `frontend/index.vue` + `runtime/index.ts`：轻量能力调用界面，不改框架前端。
- `sandbox/test_module.py`：契约测试覆盖 image analyze、video keyframes、vlm refine、扩展名类型解析。
- `README.md`：说明层次边界、schema、能力、验证和后续 OpenCV/Pillow/OCR/embedding/ASR/VLM 接入建议。

# 验证了什么

- ruff lint：所有新增 Python 文件通过。
- sandbox pytest：`modules/media-intelligence/sandbox/test_module.py` 4 passed。
- capabilities scan：工具台能从 manifest 扫到 8 个 `media-intelligence` actions。
- `/api/health` probe：200 ok。
- routes scan 当前返回空，因为常驻后端尚未重启/重载新 manifest/router；这是新增模块接入的预期限制，不代表 sandbox 契约失败。

# 边界与风险

本任务只新增/修改 `modules/media-intelligence/**` 和项目记忆。共享工作区存在其他 worker 的并发 dirty 文件，`finish_task` 总状态因此为 false，但 forbidden_hits 为 0，我未修改 backend/app、frontend/src、image-vision、media-asr、image-gen、knowledge 等禁止范围。后续若要活系统调用新 HTTP/capability，需要重启或触发后端模块 manifest/router 重载。当前 provider 是占位实现，真实算法接入需按 README 的 provider 边界逐层替换。
