"""本地预览。静态页面独立运行，基金查询转发给现有项目后端。"""

from __future__ import annotations

import json
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = 5174
BACKEND = f"http://{HOST}:8000"
FIELDS = {"/api/review": {"fund_code", "month"}, "/api/portfolio/review": {"weights", "month"}}
ROOT = Path(__file__).resolve().parent


class PreviewHandler(SimpleHTTPRequestHandler):
    def do_POST(self) -> None:
        expected = FIELDS.get(self.path)
        if expected is None:
            self.respond(404, {"error": {"message": "预览不支持此接口"}})
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 64_000:
                raise ValueError
            payload = json.loads(self.rfile.read(size))
            if not isinstance(payload, dict) or set(payload) != expected:
                raise ValueError
            if self.path == "/api/portfolio/review":
                weights = payload.get("weights")
                if not isinstance(weights, dict) or not all(
                    isinstance(value, (int, float)) and not isinstance(value, bool)
                    for value in weights.values()
                ):
                    raise ValueError
        except (ValueError, UnicodeError):
            self.respond(400, {"error": {"message": "只允许传递基金代码、月份或期初权重"}})
            return

        request = Request(
            BACKEND + self.path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=220) as response:
                self.respond(response.status, response.read())
        except HTTPError as error:
            self.respond(error.code, error.read())
        except (URLError, TimeoutError):
            self.respond(
                502,
                {"error": {"message": "本机项目后端未响应，请确认 8000 端口的服务已启动。"}},
            )

    def respond(self, status: int, content: bytes | dict) -> None:
        body = content if isinstance(content, bytes) else json.dumps(content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with ThreadingHTTPServer((HOST, PORT), partial(PreviewHandler, directory=str(ROOT))) as server:
        print(f"Preview listening on http://{HOST}:{PORT}/", flush=True)
        server.serve_forever()
