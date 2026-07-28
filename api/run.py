"""
Vercel Python serverless: after-close run_once (shadow by default).

GET/POST /api/run
Auth: Authorization: Bearer $CRON_SECRET (Vercel Cron) or x-hosted-secret.
"""

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hosted import authorize_cron, json_response, result_to_dict, run_after_close


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return  # quieter logs; never print secrets

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
            result = run_after_close()
            code = 200 if result.status not in ("error",) else 500
            json_response(self, code, result_to_dict(result))
        except Exception as exc:  # noqa: BLE001
            json_response(self, 500, {"error": str(exc), "status": "error"})
