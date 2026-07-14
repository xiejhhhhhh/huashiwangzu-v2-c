# browser-tools — 浏览器工具

隔离浏览器会话工具：打开 URL、点击/输入、截图、下载、提取文本，支持 JS 渲染和登录态页面。

## 对外能力

| 能力 | 说明 |
|------|------|
| `click` | 点击页面元素。支持 CSS selector 或按可见文本点击。 |
| `close` | 关闭浏览器会话，释放隔离上下文资源。 |
| `download` | 下载文件到工作区。支持浏览器上下文下载或直链 HTTP 下载；session_id 与 url 至少提供一个。 |
| `list_links` | 列出当前页面的可见链接（不含 Cookie/隐私数据）。 |
| `open` | 在隔离浏览器中打开 URL。适用于 JS 渲染页面、登录态页面。Cookie/localStorage 不返回给调用方。 |
| `read_text` | 提取当前页面的可见文本内容（截断保护）。返回标题/URL/可见文本。 |
| `screenshot` | 截图并保存到工作区（非 base64）。用 terminal-tools:publish 交付桌面。 |
| `type` | 向输入框输入文本。先清空再输入，带打字延迟。 |
| `wait_for` | 等待页面元素出现/导航完成。 |

## 接口

后端前缀：`/api/browser-tools`

| 路径族 | 方法 |
|------|------|
| /click | POST |
| /close | POST |
| /download | POST |
| /health | GET |
| /list-links | POST |
| /open | POST |
| /read-text | POST |
| /screenshot | POST |
| /type | POST |
| /wait-for | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/browser-tools/sandbox/test_module.py
# No frontend sandbox build for this module
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module browser-tools --check
```
