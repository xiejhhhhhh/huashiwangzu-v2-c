# media-asr — Media Audio/Video Speech Recognition

Extract audio from video files and transcribe audio/video to timestamped text via mlx_whisper. Designed as both a standalone desktop workspace and a framework capability for Agent discovery.

## UI Workspace

A ready-to-use Vue 3 workspace (`frontend/index.vue`) with:

| Feature | Description |
|---------|-------------|
| Mode selector | 视频转文字 / 仅提取音频 / 音频转文字 |
| File selection | Enter a file_id directly or upload a file via the framework |
| Parameters | Audio format, sample rate, Whisper model, language, save toggles |
| Result display | Full transcript, timestamped segment table, saved file IDs |

No Douyin download support. No cookie/credential login.

## Capabilities

| Action | Description | Input |
|--------|-------------|-------|
| `extract_audio` | Extract audio track from video | `file_id`, `sample_rate`, `audio_format`, `save_file`, `folder_id` |
| `transcribe_audio` | Transcribe audio to timestamped text | `file_id`, `model`, `language`, `save_text`, `folder_id` |
| `transcribe_video` | Extract + transcribe in one step | `file_id`, `model`, `sample_rate`, `audio_format`, `language`, `save_audio`, `save_text`, `folder_id` |

All capabilities require `editor` role (they may create framework files). Called from the frontend via `platform.modules.call('media-asr', action, params)`.

## HTTP Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/media-asr/health` | Health check |
| POST | `/api/media-asr/extract-audio` | Extract audio from video |
| POST | `/api/media-asr/transcribe-audio` | Transcribe audio file |
| POST | `/api/media-asr/transcribe-video` | Transcribe video file directly |

## Dependencies

- `ffmpeg` (system) — audio extraction
- `mlx_whisper` (Python, Apple Silicon) — local transcription
- No network API keys required

## Supported Formats

| Category | Formats |
|----------|---------|
| Video input | mp4, mov, m4v, webm, mkv, avi |
| Audio input | wav, mp3, m4a, aac, flac, ogg |
| Audio output | wav (default), mp3, m4a, flac, ogg |

## Architecture

Video/audio reading uses `run_uploaded_file_capability` which internally calls `check_file_access` for security. Saved audio/text files use `upload_file_from_path` for content-addressed storage.

Temporary files are handled in `tempfile.TemporaryDirectory()` and cleaned up automatically.

The UI communicates with the backend exclusively via `platform.modules.call` (for cross-module capability invocation) and `platform.files` (for file upload/detail). No direct HTTP calls bypassing the framework path.
