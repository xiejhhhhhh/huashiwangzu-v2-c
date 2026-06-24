---
name: file-analysis
description: 上传文件后调解析器 + 知识库分析的完整工作流
allowed-tools:
  - desktop-tools__read_file
  - knowledge__search
effort: 2
enabled: true
---

## File Analysis Workflow

When the user uploads or asks about a specific file, follow this workflow:

### Step 1: Read the file
Use `desktop-tools__read_file` with the `file_id` to get the file's text content. Check the `mime_type` to understand the format.

### Step 2: Knowledge base cross-reference
If the file content mentions products, brands, or internal terms, use `knowledge__search` to cross-reference against the company knowledge base.

### Step 3: Analyze and summarize
Provide a structured analysis:
- **Summary**: 2-3 sentence overview of what the file contains
- **Key points**: Bullet points of important information
- **Cross-references**: If knowledge base matches were found, list them with source attribution

### Notes
- For Excel/CSV files, focus on data patterns and anomalies
- For PDFs, focus on the narrative content and conclusions
- Always cite sources when referencing knowledge base content
