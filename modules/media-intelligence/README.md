# media-intelligence — Media Intelligence

图片/视频智能分析：本地特征 + 规则摘要 + 可选 VLM 精修，支持关键帧提取。

## 对外能力

| 能力 | 说明 |
|------|------|
| `analyze_image` | Analyze an uploaded image through local facts, rule-based summary, and optional VLM refine layers |
| `analyze_video` | Analyze an uploaded video with ffprobe metadata, timeline markers, summary, and optional VLM refine |
| `detect_objects` | Return object detections or structured degraded status when no detector is configured |
| `embed_image` | Return a local image fingerprint vector for dedupe-oriented contract testing |
| `extract_keyframes` | Extract ffprobe-derived timeline keyframe markers from a video file |
| `ocr` | Run OCR layer contract for image/video files; returns structured degraded status when OCR is not configured |
| `summarize_media` | Summarize a media file or existing media-intelligence analysis result |
| `vlm_refine` | Refine an existing media-intelligence analysis result through the VLM layer contract |

## 接口

后端前缀：`/api/media-intelligence`

| 路径族 | 方法 |
|------|------|
| /analyze-image | POST |
| /analyze-video | POST |
| /detect-objects | POST |
| /embed-image | POST |
| /extract-keyframes | POST |
| /health | GET |
| /ocr | POST |
| /summarize-media | POST |
| /vlm-refine | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/media-intelligence/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-intelligence --check
```
