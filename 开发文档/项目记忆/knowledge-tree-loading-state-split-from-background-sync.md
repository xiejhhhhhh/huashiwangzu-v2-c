---
name: "knowledge tree loading state split from background sync"
type: task
tags: ["knowledge", "frontend", "loading", "tree", "bugfix"]
created: 2026-06-26
agent: codex
---

Knowledge module tree UI was stuck showing '加载中…' because the sidebar used `!fileTree.length` as the loading condition and `loadFileTree()` kept later handshake/auto-registration work inside the same blocking path. Fixed in `modules/knowledge/frontend/index.vue` by introducing `fileTreeLoading`, showing a separate empty state when the tree is empty, and moving handshake/auto-registration into a background async task so the tree renders as soon as the folder list returns. Build verification was attempted; repo-wide frontend build still fails on an unrelated `modules/im/frontend/index.vue` import resolution issue (`element-plus/es`).
