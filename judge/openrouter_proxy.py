from __future__ import annotations

import hmac
import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


_HOP_BY_HOP_HEADERS = {
    "connection",
    "content-length",
    "host",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


class UsageMeter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._prompt_tokens = 0
        self._completion_tokens = 0
        self._total_tokens = 0
        self._cost = 0.0
        self._saw_usage = False
        self._saw_cost = False

    def record(self, body: bytes, content_type: str) -> None:
        for payload in self._payloads(body, content_type):
            usage = payload.get("usage")
            if not isinstance(usage, dict):
                continue
            prompt = self._integer(usage.get("prompt_tokens"))
            completion = self._integer(usage.get("completion_tokens"))
            total = self._integer(usage.get("total_tokens"))
            cost = usage.get("cost")
            with self._lock:
                self._saw_usage = True
                self._prompt_tokens += prompt
                self._completion_tokens += completion
                self._total_tokens += total if total else prompt + completion
                if isinstance(cost, (int, float)) and not isinstance(cost, bool):
                    self._cost += float(cost)
                    self._saw_cost = True

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "prompt_tokens": self._prompt_tokens if self._saw_usage else None,
                "completion_tokens": self._completion_tokens if self._saw_usage else None,
                "total_tokens": self._total_tokens if self._saw_usage else None,
                "llm_cost_usd": self._cost if self._saw_cost else None,
            }

    @staticmethod
    def _integer(value: object) -> int:
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0

    @staticmethod
    def _payloads(body: bytes, content_type: str) -> list[dict[str, object]]:
        texts: list[str]
        decoded = body.decode("utf-8", errors="replace")
        if "text/event-stream" in content_type:
            texts = [line[5:].strip() for line in decoded.splitlines() if line.startswith("data:")]
        else:
            texts = [decoded]
        payloads = []
        for text in texts:
            if not text or text == "[DONE]":
                continue
            try:
                value = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                payloads.append(value)
        return payloads


class OpenRouterProxy:
    def __init__(
        self,
        upstream_base_url: str,
        upstream_key: str,
        client_host: str = "host.docker.internal",
    ) -> None:
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self.upstream_key = upstream_key
        self.client_host = client_host
        self.access_token = secrets.token_urlsafe(32)
        self.usage = UsageMeter()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def base_url(self) -> str:
        if self._server is None:
            raise RuntimeError("proxy is not running")
        upstream_path = urlsplit(self.upstream_base_url).path.rstrip("/")
        return f"http://{self.client_host}:{self._server.server_port}{upstream_path}"

    def __enter__(self) -> OpenRouterProxy:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                proxy._forward(self)

            def do_POST(self) -> None:
                proxy._forward(self)

            def log_message(self, format: str, *args: object) -> None:
                return

        self._server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _forward(self, handler: BaseHTTPRequestHandler) -> None:
        expected = f"Bearer {self.access_token}"
        provided = handler.headers.get("Authorization", "")
        if not hmac.compare_digest(provided, expected):
            self._send(handler, 401, {"Content-Type": "application/json"}, b'{"error":"unauthorized"}')
            return

        length = int(handler.headers.get("Content-Length", "0"))
        body = handler.rfile.read(length) if length else b""
        body = self._request_usage(body, handler.headers.get("Content-Type", ""))
        headers = {
            name: value
            for name, value in handler.headers.items()
            if name.lower() not in _HOP_BY_HOP_HEADERS and name.lower() != "authorization"
        }
        headers["Authorization"] = f"Bearer {self.upstream_key}"
        headers["Accept-Encoding"] = "identity"
        target = self._target_url(handler.path)
        request = Request(target, data=body if handler.command != "GET" else None, headers=headers, method=handler.command)
        try:
            with urlopen(request, timeout=600) as response:
                response_body = response.read()
                response_headers = dict(response.headers.items())
                status = response.status
        except HTTPError as exc:
            response_body = exc.read()
            response_headers = dict(exc.headers.items())
            status = exc.code
        except (OSError, URLError) as exc:
            response_body = json.dumps({"error": f"upstream request failed: {exc}"}).encode()
            response_headers = {"Content-Type": "application/json"}
            status = 502
        self.usage.record(response_body, response_headers.get("Content-Type", ""))
        self._send(handler, status, response_headers, response_body)

    def _target_url(self, request_path: str) -> str:
        upstream_path = urlsplit(self.upstream_base_url).path.rstrip("/")
        suffix = request_path[len(upstream_path) :] if request_path.startswith(upstream_path) else request_path
        return self.upstream_base_url + suffix

    @staticmethod
    def _request_usage(body: bytes, content_type: str) -> bytes:
        if not body or "application/json" not in content_type:
            return body
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return body
        if not isinstance(payload, dict):
            return body
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            usage = {}
            payload["usage"] = usage
        usage["include"] = True
        return json.dumps(payload, separators=(",", ":")).encode()

    @staticmethod
    def _send(
        handler: BaseHTTPRequestHandler,
        status: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        handler.send_response(status)
        for name, value in headers.items():
            if name.lower() not in _HOP_BY_HOP_HEADERS and name.lower() != "content-encoding":
                handler.send_header(name, value)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
