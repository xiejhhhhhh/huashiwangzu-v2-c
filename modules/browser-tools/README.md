# browser-tools

## Responsibility

`browser-tools` is a background capability service in the V2 desktop/module architecture. It is declared by `manifest.json` and must be consumed through the framework runtime, HTTP router, or capability registry rather than direct cross-module imports.

## Public Capabilities

| Capability | min_role | Notes |
|---|---|---|
| `browser-tools:open` | viewer | 在隔离浏览器中打开 URL。适用于 JS 渲染页面、登录态页面。Cookie/localStorage 不返回给调用方。 |
| `browser-tools:read_text` | viewer | 提取当前页面的可见文本内容（截断保护）。返回标题/URL/可见文本。 |
| `browser-tools:list_links` | viewer | 列出当前页面的可见链接（不含 Cookie/隐私数据）。 |
| `browser-tools:click` | viewer | 点击页面元素。支持 CSS selector 或按可见文本点击。 |
| `browser-tools:type` | viewer | 向输入框输入文本。先清空再输入，带打字延迟。 |
| `browser-tools:wait_for` | viewer | 等待页面元素出现/导航完成。 |
| `browser-tools:screenshot` | viewer | 截图并保存到工作区（非 base64）。用 terminal-tools:publish 交付桌面。 |
| `browser-tools:download` | viewer | 下载文件到工作区。支持浏览器上下文下载或直链 HTTP 下载；session_id 与 url 至少提供一个。 |
| `browser-tools:close` | viewer | 关闭浏览器会话，释放隔离上下文资源。 |

## Boundaries

- Business logic stays inside this module directory.
- Cross-module access must go through the framework capability registry or runtime SDK.
- Framework file content access must preserve `check_file_access` semantics when `file_id` is used.

## Acceptance Matrix

| Area | Status | Verification |
|---|---|---|
| Manifest contract | PASS | `manifest.json` key `browser-tools`, window `background-service`, formats: Not format-bound. |
| Backend capability | PASS | 9 public action(s) declared in manifest and checked by capability drift gate. |
| Frontend entry | PASS | Background service is intentionally hidden from launcher with empty component_key. |
| File access | SKIP | Module does not directly consume framework file_id content. |
| Sandbox | PASS | `PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py` |
| Smoke | PASS | Use `call_capability` for `browser-tools:<action>` and release smoke/capability drift gates. |
| Known debt | DEBT | Keep component_key empty so the launcher never opens a blank background window. |

### Reproducible Checks

```bash
PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module browser-tools --check
backend/.venv/bin/python dev_toolkit/release_gate.py --skip-ui --preflight
```
