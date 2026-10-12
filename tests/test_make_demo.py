import base64
import http.server
import json
import socket
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "src" / "scripts"))

import simulate  # noqa: E402

TEMPLATES = ROOT / "samples" / "templates"


def make(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["make", "--no-print-directory", "-C", str(ROOT), *args],
                          capture_output=True, text=True, timeout=120)


class MakeDemoTest(unittest.TestCase):
    """The demo-<name> targets against a stand-in server that records each request."""

    def setUp(self):
        self.requests: list[tuple[str | None, dict]] = []
        requests = self.requests

        class Server(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append((self.headers.get("Authorization"), body))
                answer = json.dumps({"id": "0123abcd", "printer": body["printer"], "kind": body["kind"],
                                     "paper_mm": 100.0, "size_bytes": 2048, "expires_at": time.time() + 3600})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(answer.encode())

            def log_message(self, *args):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Server)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.server = f"DEMO_SERVER=http://127.0.0.1:{server.server_port}"

    def test_each_name_sends_its_sample_with_the_simulation_admin_token(self):
        cases = {
            "ticket": ("template", TEMPLATES / "ticket.json"),
            "text": ("text", simulate.TEXT_SAMPLE),
            "image": ("image", simulate.SAMPLE_IMAGE),
            "receipt": ("receipt", simulate.SAMPLE_RECEIPT),
        }
        for name, (kind, path) in cases.items():
            with self.subTest(name):
                self.requests.clear()
                result = make(f"demo-{name}", self.server)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("Queued 0123abcd for home", result.stdout)
                ((authorization, body),) = self.requests
                self.assertEqual(authorization, f"Bearer {simulate.ADMIN_TOKEN}")
                self.assertEqual((body["printer"], body["kind"], body["title"]), ("home", kind, name))
                if kind == "image":
                    self.assertEqual(base64.b64decode(body["image"]), path.read_bytes())
                else:
                    self.assertEqual(body["payload"], json.loads(path.read_text(encoding="utf-8")))

    def test_an_unknown_name_lists_the_valid_names_and_sends_nothing(self):
        result = make("demo-nope", self.server)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Unknown demo 'nope'. Valid names: agenda ", result.stderr)
        for name in [path.stem for path in TEMPLATES.glob("*.json")] + ["text", "image", "receipt"]:
            self.assertIn(f" {name}", result.stderr)
        self.assertEqual(self.requests, [])

    def test_a_stopped_simulation_says_to_run_make_demo(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        result = make("demo-ticket", f"DEMO_SERVER=http://127.0.0.1:{port}")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(f"The simulation is not running at http://127.0.0.1:{port}. Start it with make demo,",
                      result.stderr)

    def test_help_lists_demo_and_every_demo_name(self):
        result = make("help")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertRegex(result.stdout, r"\n  demo +Run make simulate")
        self.assertIn("demo-<name>", result.stdout)
        for name in [path.stem for path in TEMPLATES.glob("*.json")] + ["text", "image", "receipt"]:
            self.assertRegex(result.stdout, rf"\s{name}(\s|$)")


if __name__ == "__main__":
    unittest.main()
