from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from judge.docker_runner import DockerRunner
from judge.models import Limits, RuntimeConfig


@unittest.skipUnless(os.getenv("TABQA_DOCKER_INTEGRATION") == "1", "Docker integration test is opt-in")
class ProxyDockerIntegrationTests(unittest.TestCase):
    def test_container_uses_proxy_and_reports_usage(self) -> None:
        received_authorization: list[str] = []

        class UpstreamHandler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                self.rfile.read(length)
                received_authorization.append(self.headers["Authorization"])
                body = json.dumps(
                    {
                        "choices": [{"message": {"content": "ok"}}],
                        "usage": {
                            "prompt_tokens": 7,
                            "completion_tokens": 3,
                            "total_tokens": 10,
                            "cost": 0.001,
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
        image_tag = f"tabqa-proxy-test:{uuid.uuid4().hex[:12]}"
        runner = DockerRunner(Limits(run_seconds=60))
        try:
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                context = root / "context"
                context.mkdir()
                (context / "Dockerfile").write_text(
                    'FROM python:3.12.8-slim\nCOPY main.py /main.py\nENTRYPOINT ["python", "/main.py"]\n',
                    encoding="utf-8",
                )
                (context / "main.py").write_text(
                    """import argparse, csv, json, urllib.request
p=argparse.ArgumentParser()
p.add_argument('--xlsx-dir'); p.add_argument('--queries'); p.add_argument('--output')
p.add_argument('--openrouter-key'); p.add_argument('--openrouter-model'); p.add_argument('--openrouter-base-url')
a=p.parse_args()
r=urllib.request.Request(a.openrouter_base_url+'/chat/completions', data=b'{\"model\":\"x\"}', headers={'Authorization':'Bearer '+a.openrouter_key,'Content-Type':'application/json'})
with urllib.request.urlopen(r) as response: json.load(response)
with open(a.output, 'w', newline='') as output: csv.writer(output).writerows([['id','answer'],['1','ok']])
""",
                    encoding="utf-8",
                )
                xlsx_dir = root / "xlsx"
                output_dir = root / "output"
                xlsx_dir.mkdir()
                output_dir.mkdir()
                queries = root / "queries.json"
                queries.write_text('[{"id":"1"}]', encoding="utf-8")
                build = runner.build(context, image_tag, root / "build.out", root / "build.err")
                self.assertIsNone(build.status)
                outcome = runner.run(
                    image_tag,
                    "tabqa-proxy-integration",
                    xlsx_dir,
                    queries,
                    output_dir,
                    RuntimeConfig(
                        "real-secret",
                        "model",
                        f"http://127.0.0.1:{upstream.server_port}/api/v1",
                    ),
                    root / "run.out",
                    root / "run.err",
                )
                self.assertIsNone(outcome.status)
                self.assertEqual(outcome.usage["total_tokens"], 10)  # type: ignore[index]
                self.assertEqual(outcome.usage["llm_cost_usd"], 0.001)  # type: ignore[index]
                self.assertEqual(received_authorization, ["Bearer real-secret"])
        finally:
            runner.cleanup()
            subprocess.run(["docker", "image", "rm", "--force", image_tag], capture_output=True)
            upstream.shutdown()
            upstream.server_close()
            thread.join(timeout=5)
