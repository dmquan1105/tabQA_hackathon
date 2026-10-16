from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from judge.openrouter_proxy import OpenRouterProxy


class OpenRouterProxyTests(unittest.TestCase):
    def test_forwards_with_real_key_and_records_usage(self) -> None:
        received: dict[str, object] = {}

        class UpstreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                received["authorization"] = self.headers["Authorization"]
                received["body"] = json.loads(self.rfile.read(length))
                body = json.dumps(
                    {
                        "choices": [{"message": {"content": "answer"}}],
                        "usage": {
                            "prompt_tokens": 10,
                            "completion_tokens": 4,
                            "total_tokens": 14,
                            "cost": 0.0025,
                        },
                    }
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
        thread = threading.Thread(target=upstream.serve_forever, daemon=True)
        thread.start()
        try:
            upstream_url = f"http://127.0.0.1:{upstream.server_port}/api/v1"
            with OpenRouterProxy(upstream_url, "real-key", client_host="127.0.0.1") as proxy:
                request = Request(
                    proxy.base_url + "/chat/completions",
                    data=b'{"model":"test"}',
                    headers={
                        "Authorization": f"Bearer {proxy.access_token}",
                        "Content-Type": "application/json",
                    },
                    method="POST",
                )
                with urlopen(request) as response:
                    self.assertEqual(response.status, 200)
                usage = proxy.usage.snapshot()
        finally:
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)

        self.assertEqual(received["authorization"], "Bearer real-key")
        self.assertEqual(received["body"]["usage"], {"include": True})  # type: ignore[index]
        self.assertEqual(usage["prompt_tokens"], 10)
        self.assertEqual(usage["completion_tokens"], 4)
        self.assertEqual(usage["total_tokens"], 14)
        self.assertEqual(usage["llm_cost_usd"], 0.0025)

    def test_rejects_unknown_proxy_token(self) -> None:
        with OpenRouterProxy("http://127.0.0.1:1/api/v1", "real-key", client_host="127.0.0.1") as proxy:
            request = Request(
                proxy.base_url + "/chat/completions",
                data=b"{}",
                headers={"Authorization": "Bearer wrong-key", "Content-Type": "application/json"},
                method="POST",
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request)
            self.assertEqual(raised.exception.code, 401)
