# Module Map

Generated from `modules/*/manifest.json`. Refresh with `docs_sync(scope="module_map")`.

Modules are physically flat under `modules/{key}`. `module_family` is a logical grouping only; same-family modules still call each other through the capability bus and must not import or read each other's tables directly.

## Summary

- Total modules: 35
- Public capabilities: 189
- Entry cleanup rule: parser/provider/service/demo modules stay out of the launcher unless explicitly justified.

## Agent / Workflow

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `agent` | AI 助手 | `orchestrator` | `core` | launcher, desktop | yes | 42 | `modules/agent/README.md` |
| `memory` | 记忆 | `service` | `background` | background/file/capability | yes | 19 | `modules/memory/README.md` |
| `scheduler` | 定时任务 | `service` | `background` | background/file/capability | yes | 3 | `modules/scheduler/README.md` |

## Knowledge / Content Intelligence

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `knowledge` | 知识库 | `orchestrator` | `core` | launcher, desktop | yes | 16 | `modules/knowledge/README.md` |
| `structured-parser` | Structured Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/structured-parser/README.md` |

## Desktop / Viewer / Editor

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `text-editor` | 文本编辑器 | `editor` | `active` | launcher | no | 0 | `modules/text-editor/README.md` |
| `desktop-tools` | Desktop Tools | `service` | `core` | background/file/capability | yes | 15 | `modules/desktop-tools/README.md` |
| `doc-viewer` | 文档查看器 | `viewer` | `active` | launcher | no | 0 | `modules/doc-viewer/README.md` |
| `image-viewer` | 图片查看器 | `viewer` | `active` | launcher | no | 0 | `modules/image-viewer/README.md` |
| `pdf-viewer` | PDF 查看器 | `viewer` | `active` | launcher | no | 0 | `modules/pdf-viewer/README.md` |
| `ppt-viewer` | 演示文稿查看器 | `viewer` | `active` | launcher | no | 0 | `modules/ppt-viewer/README.md` |

## Office / Parser / Document

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `docs-open` | 文档开放接口 | `app` | `active` | launcher | yes | 3 | `modules/docs-open/README.md` |
| `excel-engine` | Excel 编辑器 | `editor` | `active` | launcher | yes | 13 | `modules/excel-engine/README.md` |
| `csv-parser` | CSV Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/csv-parser/README.md` |
| `docx-parser` | DOCX Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/docx-parser/README.md` |
| `email-parser` | Email Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/email-parser/README.md` |
| `markdown-parser` | Markdown Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/markdown-parser/README.md` |
| `pdf-parser` | PDF Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/pdf-parser/README.md` |
| `pptx-parser` | PPTX Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/pptx-parser/README.md` |
| `text-parser` | Text/Markdown Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/text-parser/README.md` |
| `xlsx-parser` | XLSX/CSV Parser | `parser` | `background` | background/file/capability | yes | 1 | `modules/xlsx-parser/README.md` |
| `office-gen` | Office Document Generator | `provider` | `background` | background/file/capability | yes | 8 | `modules/office-gen/README.md` |

## AI Media Providers

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `media-intelligence` | Media Intelligence | `orchestrator` | `active` | launcher | yes | 8 | `modules/media-intelligence/README.md` |
| `image-gen` | Image Generation | `provider` | `background` | background/file/capability | yes | 3 | `modules/image-gen/README.md` |
| `image-vision` | Image Vision | `provider` | `background` | background/file/capability | yes | 1 | `modules/image-vision/README.md` |
| `media-asr` | Media ASR (Audio/Video to Text) | `provider` | `background` | background/file/capability | yes | 3 | `modules/media-asr/README.md` |

## Web / Browser / External Info

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `browser-tools` | 浏览器工具 | `provider` | `background` | background/file/capability | yes | 9 | `modules/browser-tools/README.md` |
| `github-search` | GitHub 搜索 | `provider` | `background` | background/file/capability | yes | 2 | `modules/github-search/README.md` |
| `web-tools` | 联网工具 | `provider` | `background` | background/file/capability | yes | 2 | `modules/web-tools/README.md` |

## Business Apps

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `douyin-delivery` | 抖音内容与计划助手 | `app` | `active` | launcher, desktop | yes | 6 | `modules/douyin-delivery/README.md` |
| `im` | 消息 | `app` | `active` | launcher | yes | 2 | `modules/im/README.md` |
| `wechat-writer` | 公众号写作助手 | `app` | `active` | launcher | yes | 4 | `modules/wechat-writer/README.md` |

## Agent Dev Tools

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `codemap` | 代码地图 | `provider` | `background` | background/file/capability | yes | 13 | `modules/codemap/README.md` |
| `terminal-tools` | 终端工具 | `provider` | `background` | background/file/capability | yes | 8 | `modules/terminal-tools/README.md` |

## Demo

| Module | Name | Type | Status | Entry | Backend | Public actions | README |
|---|---|---|---|---|---|---:|---|
| `hello-world` | Hello World | `demo` | `demo` | background/file/capability | no | 0 | `modules/hello-world/README.md` |

