# terminal-tools — 终端工具

Workspace-bound command and file tool module for Agent execution, run_python, charts, import, and publish.

## 对外能力

| 能力 | 说明 |
|------|------|
| `chart` | 傻瓜式出图，传入数据数组和图表类型，后端用 matplotlib 出图到工作区，需 publish 才桌面可见。 |
| `exec` | 在用户工作区执行 shell 命令，返回 stdout/stderr/退出码。受路径约束、危险命令拦截、超时和输出限制。 |
| `import` | 将框架文件系统的文件拷入工作区供 CLI 处理，owner 校验。 |
| `list_workspace` | 列出用户工作区内的文件和目录。 |
| `publish` | 将工作区文件显式交付到框架文件系统（桌面可见），享受框架内容去重。 |
| `read_file` | 读用户工作区内的文件内容。 |
| `run_python` | 在用户工作区子进程执行 Python 数据分析代码。预置 pandas/numpy/matplotlib；生成图片先留在工作区，需 publish 才桌面可见。 |
| `write_file` | 写文件到用户工作区，路径自动约束在工作区内。 |

## 接口

后端前缀：`/api/terminal-tools`

| 路径族 | 方法 |
|------|------|
| /chart | POST |
| /exec | POST |
| /health | GET |
| /import | POST |
| /list-workspace | POST |
| /publish | POST |
| /read-file | POST |
| /run-python | POST |
| /write-file | POST |

## 验证

```bash
backend/.venv/bin/python scripts/check-capability-drift.py
PYTHONPATH=backend backend/.venv/bin/python modules/terminal-tools/sandbox/test_module.py
cd modules/terminal-tools/sandbox && npm run build
backend/.venv/bin/python dev_toolkit/module_sandbox_matrix.py --module terminal-tools --check
```
