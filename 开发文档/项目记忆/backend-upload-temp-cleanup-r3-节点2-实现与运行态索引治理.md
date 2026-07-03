---
name: "backend upload temp cleanup r3 节点2：实现与运行态索引治理"
type: "task"
tags: [backend, file-upload, temp-cleanup, gitignore, r3]
agent: "backend-upload-temp-cleanup-r3"
created: "2026-07-03T10:07:02.004077+00:00"
---

节点2完成：backend/app/routers/file_transfer.py 新增 _cleanup_temp_upload，并将普通上传临时文件清理放入覆盖读流、空文件、超限、mime 检测、upload_file_from_path 异常和成功路径的 finally；成功路径保持调用 upload_file_from_path 前关闭 fd。backend/tests/test_file_system_upload_download.py 增加 empty/too large/upload_file_from_path 异常三类清理测试，使用临时 UPLOAD_DIR，不碰真实 data/uploads。.gitignore 与 backend/data/.gitignore 补齐 .chunked_uploads、.tmp_downloads、.tmp_exports、.tmp_uploads、.tmp_upload_sessions、.upload_sessions、runtime/*.jsonl 等运行态规则；已用 git rm --cached 解除 backend/data 下已跟踪的 chunk、tmp_exports、gateway_traces.jsonl 索引跟踪，只移除索引不删除磁盘文件。当前无 commit。
