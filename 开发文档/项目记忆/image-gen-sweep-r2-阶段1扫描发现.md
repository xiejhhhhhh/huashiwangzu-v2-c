---
name: "image-gen sweep r2 阶段1扫描发现"
type: "task"
tags: [image-gen, module-sweep, heartbeat, scan, task_id:image-gen-sweep-20260703-r2]
agent: "codex-image-gen-sweep-20260703-r2"
created: "2026-07-03T06:59:13.947900+00:00"
---

阶段1扫描发现：1) 前端只传 aspect_ratio，但后端 GenerateRequest 默认 size=1024x1024 且解析优先 size，GenSpec 也未传 aspect_ratio，导致 portrait/landscape 实际仍可能按 square 生成；2) count/steps/size/aspect_ratio 参数缺统一转换与上限，非法值可能抛非结构化异常或引发过大产物；3) 文件产物名仅 image-gen_{timestamp_ms}_{idx}.png，并发同毫秒同用户存在 409 冲突风险；4) URL 下载失败时逐项 continue，全部失败才给笼统“未生成可用图片”，缺少失败原因记录；5) sandbox/test_module.py 使用旧的 image_urls/name/cost 假契约，没有校验当前 manifest/public_actions、image_templates 和 provider registry；6) imagegen_records 当前空表，需要修后用 placeholder fallback 跑活系统并清理生成文件/记录。下一步只改 modules/image-gen/**，补参数解析、产物命名和 sandbox 契约测试。
