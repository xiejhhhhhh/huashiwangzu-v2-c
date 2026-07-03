# web-tools — Web search and page fetching (no API key)

## Responsibility
Provides web search (DuckDuckGo HTML search) and web page content fetching for agents. No API key required — uses `ddgs` for search and `httpx + lxml` for page extraction. SSRF protection blocks internal network addresses.

## Public capabilities

| Capability | Parameters | Returns | min_role |
|---|---|---|---|
| `web-tools:search` | `query` (str), `top_k` (int, default 8, max 20) | `{results: [{title, url, snippet}], error}` | viewer |
| `web-tools:fetch` | `url` (str), `max_chars` (int, default 8000) | `{url, title, text, truncated, error}` | viewer |

## HTTP endpoints

All under `/api/web-tools`:

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Module health check |
| POST | `/search` | DuckDuckGo web search |
| POST | `/fetch` | Fetch and extract web page text content |

## Data tables
None. Stateless module.

## How to query/use
Agent discovers `web-tools__search` and `web-tools__fetch` as function tools. Call via `call_capability("web-tools", "search", {...})` or `call_capability("web-tools", "fetch", {...})`.

## Boundaries/notes
- **Search**: Uses DuckDuckGo HTML endpoint via `ddgs` library, region `cn-zh`, safesearch moderate. Tries proxy (`WEB_TOOLS_PROXY` env or `http://127.0.0.1:4780`) first, falls back to direct.
- **Fetch**: SSRF-protected via `app.core.url_safety.validate_safe_url` — blocks internal/private IP ranges (localhost, 10.x, 172.16-31.x, 192.168.x, etc.), cloud metadata endpoints (169.254.169.254), non-http(s) schemes, embedded credentials, and DNS lookups to private addresses (fail-closed on DNS failure). Redirect targets are revalidated before each hop. Rejects binary content types on both HEAD and GET. Strips script/style/nav/footer before extracting text.
- **Limits**: `top_k` must be 1-20, `max_chars` must be 1-8000, query length is capped at 500 chars, URL length is capped at 2048 chars, and response downloads are hard-capped at 5MB while streaming instead of trusting only `Content-Length`.
- **Failure semantics**: capability failures return `success:false` internally so `/api/modules/call` converts them to unified framework errors; direct HTTP endpoints raise framework `ValidationError` instead of returning 200-style fake failures.
- **Proxy**: Default proxy is `http://127.0.0.1:4780` (ClashX common port); customizable via `WEB_TOOLS_PROXY` env var.
- Background-service window type, not shown in launcher.
- Timeouts: search 10s, fetch 15s, max content 5MB.

## Verification

```bash
cd backend && .venv/bin/ruff check ../modules/web-tools/backend/router.py ../modules/web-tools/sandbox/test_module.py
cd backend && .venv/bin/python -m pytest ../modules/web-tools/sandbox/test_module.py
```

Live-stack checks:

```text
call_capability("web-tools", "fetch", {"url": "http://127.0.0.1:33000/api/health"})
call_capability("web-tools", "search", {"query": "华世王镞", "top_k": 1})
```
