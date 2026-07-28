"""
Vercel Python serverless: missed-run watchdog (~6:30pm ET).
"""

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hosted import authorize_cron, json_response
from watchdog_logic import run_watchdog


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
            json_response(self, 200, run_watchdog())
        except Exception as exc:  # noqa: BLE001
            json_response(self, 500, {"error": str(exc), "status": "error"})
