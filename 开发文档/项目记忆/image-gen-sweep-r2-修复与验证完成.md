---
name: "image-gen sweep r2 修复与验证完成"
type: "task"
tags: [image-gen, module-sweep, complete, task_id:image-gen-sweep-20260703-r2]
agent: "codex-image-gen-sweep-20260703-r2"
created: "2026-07-03T07:04:59.821124+00:00"
---

完成 image-gen r2 扫雷。问题清单：1) aspect_ratio 被 GenerateRequest 默认 size=1024x1024 吞掉，且 GenSpec 未传 aspect_ratio，导致前端 portrait/landscape 可能实际生成方图；2) count/steps/size/aspect_ratio 缺边界和结构化校验；3) 生成文件名仅 timestamp_ms+idx，并发同毫秒存在文件名冲突风险；4) provider URL 下载/保存失败时静默跳过，失败记录缺细节；5) sandbox/test_module.py 使用旧 image_urls/name/cost 假契约，没有校验当前 manifest/templates/provider registry；6) imagegen_records 空库需要验证写入链路后清理。

修复：modules/image-gen/backend/router.py 新增参数解析与尺寸解析，aspect_ratio 优先于 size，count 限 1-4，steps 限 1-100，尺寸限 256-2048；GenSpec 传入 aspect_ratio；文件名加入 uuid suffix；下载/保存失败进入 persist_errors，失败或 partial 状态写 imagegen_records 并在成功响应中给可见 error/detail。modules/image-gen/backend/providers/placeholder.py 移除未用变量。modules/image-gen/sandbox/test_module.py 重写为真实契约测试：manifest public_actions、image_templates default/provider、Liblib polling/credential 配置、placeholder provider 生成和框架 file_id 返回契约。modules/image-gen/manifest.json 与 README 同步参数边界和持久化语义。

验证：ruff check modules/image-gen/backend/router.py、providers/placeholder.py、sandbox/test_module.py 全通过；run_test modules/image-gen/sandbox/test_module.py 5 passed；直接加载修改后的模块代码执行 placeholder landscape 生成，产物尺寸 1280x720，随后清理 file row、物理文件、imagegen_records；probe /api/health 200 success；probe /api/image-gen/templates 200 success；call_capability image-gen:list_templates 200 success；db_reverse_audit 显示 imagegen_records 为空，符合测试产物已清理。finish_task 因共享工作区其他 worker 的 codemap/knowledge/office-gen/data/uploads 改动返回边界 false，本 worker 产品 diff 限定在 modules/image-gen/**。关联 commit：待主会话统一提交。
