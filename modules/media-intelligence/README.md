# media-intelligence

Media Intelligence is the contract and module skeleton for the layered media-analysis decision made on 2026-07-03:

```text
local algorithms -> small model providers -> VLM refine
```

This first version does not train or ship heavy models. It establishes the module boundary, result schema, provider registry, HTTP endpoints, cross-module capabilities, and sandbox validation with deterministic placeholders.

## Architecture

| Layer | Current implementation | Future adapter boundary |
|---|---|---|
| Local algorithms | File header metadata, deterministic keyframe records, OCR/object/embedding placeholders | OpenCV, Pillow, ffmpeg frame sampling, PaddleOCR/Tesseract, classical detectors |
| Small model providers | Deterministic summary and tags | CLIP, YOLO, lightweight image classifiers, local embedding models, ASR summary adapters |
| VLM refine | Placeholder refine stage | Framework model gateway VLM or approved local VLM adapter |

The backend keeps each layer behind `backend/providers/`. `backend/pipeline.py` owns result assembly and schema stability. `backend/router.py` owns HTTP, auth, framework file access through `run_uploaded_file_capability`, and capability registration.

## Result Schema

All analysis actions return:

```json
{
  "schema_version": "media-intelligence.analysis.v1",
  "analysis_id": "...",
  "action": "analyze_image",
  "media_type": "image",
  "source": {
    "file_id": 1,
    "file_name": "sample.png",
    "extension": "png",
    "media_type": "image",
    "size_bytes": 123,
    "head_sha256": "..."
  },
  "stages": [],
  "signals": {},
  "artifacts": {
    "keyframes": [],
    "ocr": null,
    "objects": [],
    "embedding": null
  },
  "summary": "",
  "tags": [],
  "confidence": 0.0,
  "warnings": [],
  "providers": []
}
```

`schema_version` is the compatibility anchor for Agent, knowledge, and future media indexing work.

## Capabilities

| Action | Role | Input | Notes |
|---|---|---|---|
| `analyze_image` | viewer | `file_id`, `include_embedding`, `refine` | Local metadata + small-model summary + optional VLM refine |
| `analyze_video` | viewer | `file_id`, `max_keyframes`, `refine` | Local metadata/keyframes + small-model summary + optional VLM refine |
| `extract_keyframes` | viewer | `file_id`, `max_keyframes` | Placeholder records only; no frame files yet |
| `ocr` | viewer | `file_id` | OCR contract placeholder |
| `embed_image` | viewer | `file_id`, `dimensions` | Deterministic placeholder vector |
| `detect_objects` | viewer | `file_id` | Filename/metadata hint placeholder |
| `summarize_media` | viewer | `file_id` or `analysis` | Summarize from file or existing analysis payload |
| `vlm_refine` | viewer | `analysis`, `prompt` | Refine an existing result through the VLM contract |

All file-based actions use the framework uploaded-file runner, which performs file access checks before reading disk. The module does not import other modules and does not read their tables.

## HTTP Endpoints

| Method | Path |
|---|---|
| GET | `/api/media-intelligence/health` |
| POST | `/api/media-intelligence/analyze-image` |
| POST | `/api/media-intelligence/analyze-video` |
| POST | `/api/media-intelligence/extract-keyframes` |
| POST | `/api/media-intelligence/ocr` |
| POST | `/api/media-intelligence/embed-image` |
| POST | `/api/media-intelligence/detect-objects` |
| POST | `/api/media-intelligence/summarize-media` |
| POST | `/api/media-intelligence/vlm-refine` |

## Supported Formats

| Type | Formats |
|---|---|
| Image | jpg, jpeg, png, gif, webp, bmp, ico |
| Video | mp4, mov, m4v, webm, mkv, avi |

## Verification

```bash
PYTHONPATH=. backend/.venv/bin/python -m pytest modules/media-intelligence/sandbox/test_module.py
mcp lint path=modules/media-intelligence/backend/router.py,modules/media-intelligence/backend/pipeline.py,modules/media-intelligence/backend/providers/base.py,modules/media-intelligence/backend/providers/local_algorithms.py,modules/media-intelligence/backend/providers/small_model.py,modules/media-intelligence/backend/providers/vlm.py,modules/media-intelligence/backend/providers/registry.py
```

Main-stack capability validation can run after the backend has loaded the new manifest:

```bash
POST /api/modules/call
{
  "target_module": "media-intelligence",
  "action": "vlm_refine",
  "parameters": {
    "analysis": {
      "schema_version": "media-intelligence.analysis.v1",
      "analysis_id": "demo",
      "source": {"file_id": 0, "file_name": "demo.png", "extension": "png", "media_type": "image"},
      "stages": [],
      "warnings": [],
      "summary": "demo"
    }
  }
}
```

## Next Adapters

1. Add `opencv_keyframes` under `backend/providers/` and keep output mapped to `artifacts.keyframes`.
2. Add OCR providers under the local layer, returning `artifacts.ocr.text` and region boxes.
3. Add image embedding provider that calls the framework model service or a local CLIP adapter, preserving vector dimensions in `artifacts.embedding`.
4. Add object detection provider with normalized boxes and labels.
5. Add VLM adapter that calls the framework model gateway for costly refine only after cheap signals are present.
6. Add persistence only after schema consumers stabilize; use a `media_intelligence_*` table prefix if storage becomes necessary.
