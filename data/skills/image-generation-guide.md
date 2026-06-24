---
name: image-generation-guide
description: 使用 image-gen 模块生成图片的流程和最佳实践
allowed-tools:
  - image-gen__generate
effort: 3
enabled: true
---

## Image Generation Guide

When the user requests image generation, follow these guidelines:

### Step 1: Understand the request
Determine the subject, style, composition, and any specific elements the user wants.

### Step 2: Build the prompt
- If the user's description is in Chinese, translate it to English before sending
- Include style keywords (e.g., "photorealistic", "oil painting", "vector art")
- Specify aspect ratio if relevant (e.g., "16:9", "1:1", "9:16")
- Keep prompts clear and descriptive, avoid ambiguity

### Step 3: Call image-gen
Use `image-gen__generate` with:
- `prompt`: Your crafted English prompt
- `style`: The desired style (defaults to realistic if not specified)
- `size`: Image dimensions if the user specified

### Step 4: Present the result
- Return the generated image URL to the user
- Briefly describe what was generated
- Offer to regenerate with modifications if needed
