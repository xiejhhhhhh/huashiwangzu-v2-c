# media-intelligence

Media Intelligence is the contract and module skeleton for the layered media-analysis decision made on 2026-07-03:

```text
local algorithms -> small model providers -> VLM refine
```

This first version does not train or ship heavy models. It establishes the module boundary, result schema, provider registry, HTTP endpoints, cross-module capabilities, and sandbox validation with a real local facts layer. Missing optional dependencies return structured `degraded` reasons instead of fake success.

## Architecture

| Layer | Current implementation | Future adapter boundary |
|---|---|---|
| Local algorithms | Pillow image metadata, ffprobe video metadata, ffprobe timeline markers, image average-intensity fingerprint | OpenCV/ffmpeg thumbnail extraction, PaddleOCR/Tesseract, classical detectors |
| Small model providers | Rule-based summary and tags with structured degraded status | CLIP, YOLO, lightweight image classifiers, local embedding models, ASR summary adapters |
| VLM refine | Structured degraded result when no VLM is configured | Framework model gateway VLM or approved local VLM adapter |

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
  "degraded": [],
  "providers": []
}
```

`schema_version` is the compatibility anchor for Agent, knowledge, and future media indexing work.

## Capabilities

| Action | Role | Input | Notes |
|---|---|---|---|
| `analyze_image` | viewer | `file_id`, `include_embedding`, `refine` | Pillow metadata + local fingerprint + rule-based summary + optional VLM refine |
| `analyze_video` | viewer | `file_id`, `max_keyframes`, `refine` | ffprobe metadata/timeline markers + rule-based summary + optional VLM refine |
| `extract_keyframes` | viewer | `file_id`, `max_keyframes` | ffprobe-derived timeline markers; no frame files yet |
| `ocr` | viewer | `file_id` | Structured degraded result until OCR is configured |
| `embed_image` | viewer | `file_id`, `dimensions` | Local average-intensity fingerprint vector |
| `detect_objects` | viewer | `file_id` | Structured degraded result until a detector is configured |
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

## Local Dependencies

The module detects optional local dependencies at runtime:

| Dependency | Used for | Missing behavior | Suggested install |
|---|---|---|---|
| Pillow | Image dimensions, format, mode, frame count, local fingerprint | `degraded` with `pillow_missing` or related code | `backend/.venv/bin/python -m pip install Pillow` |
| ffprobe | Video duration, dimensions, frame rate, codec, timeline markers | `degraded` with `ffprobe_missing` | `brew install ffmpeg` |
| OCR/detector adapters | OCR text and object boxes | `degraded` with `ocr_engine_missing` / `object_detector_missing` | Wire PaddleOCR/Tesseract/OpenCV/YOLO in module providers |

## Verification

```bash
PYTHONPATH=backend:. backend/.venv/bin/python -m pytest modules/media-intelligence/sandbox/test_module.py
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

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `media-intelligence`, window `normal`, formats: jpg, jpeg, png, gif, webp, bmp, ico, mp4, mov, m4v, webm, mkv, avi. |
| Backend capability | PASS | 8 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Desktop entry component `index.vue` exists. |
| File access | PASS | Uses framework file APIs or capability bridge; file_id paths must preserve check_file_access. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/media-intelligence/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `media-intelligence:<action>` and release smoke/capability drift gates. |
| Known debt | PASS | None tracked in this matrix. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/media-intelligence/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-intelligence --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
