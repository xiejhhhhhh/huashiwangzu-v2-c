---
name: "媒体智能采用本地算法-小模型-VLM分层流水线"
type: "architecture"
tags: [media-intelligence, image-vision, video-analysis, architecture, cost-control]
agent: "codex-conductor-sweep-20260703-r2"
created: "2026-07-03T07:14:49.323073+00:00"
---

2026-07-03 讨论决定：图片/视频分析不应设计成纯 VLM 调用器，而应作为底层媒体智能流水线建设。

分层方向：
1. 确定性本地算法层：尺寸/EXIF/损坏检测/模糊度/pHash 去重/OCR/二维码条码/基础版面与颜色统计。
2. 本地小模型层：图片 embedding、目标检测、场景/素材类型分类、关键帧抽取、镜头切分、ASR/OCR 聚合、相似素材检索。
3. 业务规则层：根据本地结果判断商品图、截图、证件、发票、口播、适合投递等业务标签。
4. VLM 精判层：只处理关键帧、异常/低置信度样本、需要复杂语义描述或推理的少数内容。
5. 学习闭环层：保存用户修正、VLM 高质量结论、本地算法失败案例，未来可微调小模型。

落地原则：先做 pipeline 和数据闭环，优先接入开源小模型/算法作为可替换 provider；不要一开始从零训练模型。对外能力建议统一为 analyze_image/analyze_video/extract_keyframes/ocr/embed_image/detect_objects/summarize_media/vlm_refine，供 Agent、知识库、素材管理、抖音投递共享。
