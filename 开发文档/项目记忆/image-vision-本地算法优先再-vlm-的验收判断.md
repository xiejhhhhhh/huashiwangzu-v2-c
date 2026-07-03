---
name: "image-vision 本地算法优先再 VLM 的验收判断"
type: "architecture"
tags: [image-vision, local-first, vlm, cost, architecture, r2]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T08:08:37.327928+00:00"
---

主会话验收 image-vision r2：认可当前路线为本地确定性/轻量算法先处理，必要时再 VLM。已落地本地 Pillow 分析器，输出尺寸、格式、颜色、亮度、透明度、边缘密度、哈希、EXIF、visual_profile 等机器可消费事实；analysis_mode=local|auto|semantic，local 模式明确 external_vlm_calls=0，auto 由 should_use_vlm 决策，semantic 才强制尝试 VLM。当前未引入训练框架，避免复杂依赖；后续 OCR、小检测器或本地小模型可插在 local_analysis 与 VLM 决策之间，不必改 describe 能力契约。验收：ruff 通过；sandbox 2 passed；sandbox frontend build 通过；live file_id=2014 local-only 返回 local_analysis 且 external_vlm_calls=0；坏 file_id、坏 analysis_mode 均 422。
