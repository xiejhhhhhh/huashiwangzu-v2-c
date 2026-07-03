# Image Vision Module

Image Vision analyzes uploaded image files through a local-first, low-cost pipeline.

## Architecture

The module always extracts deterministic local facts before considering any model call:

1. Validate `file_id`, caller, owner/share access, extension, and storage path through the framework uploaded-file runner.
2. Use Pillow locally to extract dimensions, format, mode, animation frames, transparency ratio, brightness, contrast, saturation, dominant colors, edge density, perceptual hashes, EXIF presence, and a coarse visual profile.
3. Decide whether semantic interpretation is needed.
4. Call the framework vision model only when the decision says the image is content-rich enough, or when callers explicitly request `analysis_mode="semantic"`.
5. Return local facts, strategy/cost metadata, warnings, blocks, and resources. If VLM fails, the response degrades honestly to local analysis instead of pretending semantic analysis succeeded.

This keeps the current implementation lightweight. Future OCR, object detection, small local vision models, or specialized providers can be added after the local analyzer and before the VLM decision without changing the public capability contract.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/image-vision/health` | GET | Module health check |
| `/api/image-vision/describe` | POST | Analyze an image file by `file_id` |

Request:

```json
{
  "file_id": 123,
  "analysis_mode": "auto",
  "prompt": "optional semantic focus"
}
```

`analysis_mode` values:

| Mode | Behavior |
|------|----------|
| `auto` | Default. Local facts first; VLM only for content-rich images that likely need semantic interpretation. |
| `local` | Never calls VLM. Returns deterministic local facts only. |
| `semantic` | Calls VLM after local facts unless the model gateway fails, then degrades to local facts with warnings. |

## Capability

| Module | Action | Input | Output |
|--------|--------|-------|--------|
| `image-vision` | `describe` | `{"file_id": int, "analysis_mode": "auto|local|semantic", "prompt": string}` | Blocks, resources, local analysis, semantic description, strategy metadata |

## Output Fields

Important top-level fields:

| Field | Meaning |
|-------|---------|
| `description` | Final user-readable description. Semantic text is prepended when VLM succeeds; otherwise this is the local summary. |
| `local_analysis` | Deterministic facts from Pillow and lightweight algorithms. |
| `semantic_description` | VLM-only semantic text, or `null` when not called or unavailable. |
| `analysis_strategy` | Mode, local analyzer version, VLM decision, whether VLM was attempted/used, and external call count. |
| `warnings` | Honest degradation notes, such as VLM or resource persistence failure. |

## Dependencies

- `Pillow` / `PIL` from the backend environment.
- Framework uploaded-file runner for `check_file_access` and path safety.
- Framework model gateway only when semantic interpretation is needed.

## Format Support

- `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.ico`

## Verification

```bash
# Python lint
python3.14 -m ruff check modules/image-vision/backend/router.py modules/image-vision/backend/image_analysis.py modules/image-vision/sandbox/test_module.py

# Sandbox backend contract test
backend/.venv/bin/python modules/image-vision/sandbox/test_module.py

# Sandbox frontend build
cd modules/image-vision/sandbox && npm run build

# Health check
curl http://127.0.0.1:33000/api/image-vision/health

# Local-only analysis
curl -X POST http://127.0.0.1:33000/api/image-vision/describe \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"file_id": <id>, "analysis_mode": "local"}'
```
