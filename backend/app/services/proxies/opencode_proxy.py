"""
OpenCode Go 云端模型代理。
在指定端口提供 OpenAI 兼容 /v1/chat/completions，请求转发到 opencode.ai。

可作为 module 直接启动:
    python3 -m app.services.proxies.opencode_proxy --port 30006
"""

import argparse
import json
import logging
import os
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any

import httpx

logging.basicConfig(level=logging.INFO, format="%(asctime)s [opencode-proxy] %(levelname)s %(message)s")
logger = logging.getLogger("opencode-proxy")

API_URL = "https://opencode.ai/zen/go/v1/chat/completions"
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

MODEL_MAP = {
    "deepseek-v4-flash": "deepseek-v4-flash",
    "deepseek-v4-pro": "deepseek-v4-pro",
    "qwen-72b": "deepseek-v4-flash",
}


class ProxyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/v1/models":
            self._send_json(200, {
                "object": "list",
                "data": [
                    {"id": "deepseek-v4-flash", "object": "model"},
                    {"id": "deepseek-v4-pro", "object": "model"},
                ],
            })
        elif self.path == "/health":
            self._send_json(200, {"status": "ok"})
        else:
            self._send_json(404, {"error": "Not found"})

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_json(404, {"error": "Not found"})
            return
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            req = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return
        stream = req.get("stream", False)
        model = req.get("model", "deepseek-v4-flash")
        api_model = MODEL_MAP.get(model, "deepseek-v4-flash")
        api_key = DEEPSEEK_API_KEY or self._load_api_key()
        if stream:
            self._handle_stream(req, api_model, api_key)
        else:
            self._handle_chat(req, api_model, api_key)

    def _load_api_key(self) -> str:
        try:
            config_path = os.path.expanduser("~/.config/opencode/opencode.json")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    cfg = json.load(f)
                providers = cfg.get("providers", {})
                for p in providers.values():
                    token = p.get("apiKey") or p.get("token") or ""
                    if token:
                        return token
        except Exception as e:
            logger.warning("Failed to load API key: %s", e)
        return ""

    def _handle_chat(self, req: dict, api_model: str, api_key: str):
        try:
            with httpx.Client(timeout=120) as client:
                resp = client.post(
                    API_URL,
                    json={
                        "model": api_model,
                        "messages": req.get("messages", []),
                        "max_tokens": req.get("max_tokens", 4096),
                        "temperature": req.get("temperature", 0.7),
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                )
                self._send_json(resp.status_code, resp.json())
        except Exception as e:
            self._send_json(502, {"error": str(e)})

    def _handle_stream(self, req: dict, api_model: str, api_key: str):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            with httpx.Client(timeout=300) as client:
                with client.stream(
                    "POST", API_URL,
                    json={
                        "model": api_model,
                        "messages": req.get("messages", []),
                        "max_tokens": req.get("max_tokens", 4096),
                        "temperature": req.get("temperature", 0.7),
                        "stream": True,
                    },
                    headers={"Authorization": f"Bearer {api_key}"},
                ) as upstream:
                    for chunk in upstream.iter_lines():
                        if chunk:
                            self.wfile.write(f"data: {chunk}\n\n".encode())
                            self.wfile.flush()
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except Exception as e:
            self.wfile.write(f"data: {{\"error\": \"{e}\"}}\n\n".encode())
            self.wfile.flush()

    def _send_json(self, status: int, data: Any):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
        self.wfile.flush()

    def log_message(self, fmt, *args):
        logger.info(fmt, *args)


def main():
    parser = argparse.ArgumentParser(description="OpenCode Go Proxy")
    parser.add_argument("--port", type=int, default=30006, help="Port to listen on")
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), ProxyHandler)
    logger.info("OpenCode Go proxy listening on http://127.0.0.1:%d", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
