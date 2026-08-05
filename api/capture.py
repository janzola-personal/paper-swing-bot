"""
Vercel Python serverless: morning day-start equity capture (~9:31 ET).

GET/POST /api/capture
Auth: Authorization: Bearer $CRON_SECRET
"""

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hosted import authorize_cron, json_response, results_to_dict, run_open_capture


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_GET(self):
        self._run()

    def do_POST(self):
        self._run()

    def _run(self):
        headers = {k: v for k, v in self.headers.items()}
        if not authorize_cron(headers):
            json_response(self, 401, {"error": "unauthorized"})
            return
        try:
            results = run_open_capture()
            payload = results_to_dict(results)
            bad = any(r.status == "error" for r in results)
            code = 500 if bad else 200
            json_response(self, code, payload)
        except Exception as exc:  # noqa: BLE001
            json_response(self, 500, {"error": str(exc), "status": "error"})
