# media-asr — Media ASR (Audio/Video to Text)

音视频转文字：提取音轨、语音转写为带时间戳文本。

## 对外能力

| 能力 | 说明 |
|------|------|
| `extract_audio` | Extract audio from an uploaded video file |
| `transcribe_audio` | Transcribe audio file into timestamped text |
| `transcribe_video` | Extract audio from video and transcribe in one step |

## 接口

后端前缀：`/api/media-asr`

| 路径族 | 方法 |
|------|------|
| /extract-audio | POST |
| /health | GET |
| /transcribe-audio | POST |
| /transcribe-video | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/media-asr/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module media-asr --check
```
