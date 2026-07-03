---
name: "image-vision sweep r2 local-first architecture implemented"
type: "architecture"
tags: [image-vision, local-first, vlm-cost, sandbox, verification, task_id:image-vision-sweep-20260703-r2]
agent: "codex-image-vision-sweep-20260703-r2"
created: "2026-07-03T08:00:16.258158+00:00"
---

修复节点：在 modules/image-vision 内落地本地确定性/轻量算法优先架构。新增 backend/image_analysis.py，以 Pillow 提取尺寸、格式、亮度/对比度/饱和度、透明度、主色、边缘密度、平均哈希/dhash、动画帧、EXIF 与 visual_profile；router 先产出 local_analysis，再根据 analysis_mode(auto/local/semantic) 和 local facts 决定是否调用 VLM。local 模式 external_vlm_calls=0；VLM 失败时通过 warnings/degraded 诚实降级。修复 bad file_id/analysis_mode 参数：负数/非整数/坏 mode 统一 422，不再 500。sandbox/test_module.py 改为直接测试真实本地分析器，frontend/index.vue 从模板页改为可调用 image-vision:describe 的分析面板。验证：ruff 通过；run_test modules/image-vision/sandbox/test_module.py 2 passed；backend/.venv/bin/python sandbox/test_module.py 通过；sandbox npm run build 通过；活系统 call_capability/probe 坏参数 422、file_id 999999999 404、file_id 2014 local-only 返回 local_analysis 且 external_vlm_calls=0；/api/health ok。
