"""POST /api/engine_pause — toggle pause (Bearer CRON_SECRET). Body: paused, actor."""

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from actions import set_paused
from hosted import authorize_cron, json_response


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):
        headers = {k: v for k, v in self.headers.items()}
        if not authorize_cron(headers):
            json_response(self, 401, {"error": "unauthorized"})
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            body = json.loads(raw.decode() or "{}")
            paused = bool(body.get("paused"))
            actor = str(body.get("actor") or "")
            result = set_paused(paused, actor)
            json_response(self, 200, result)
        except Exception as exc:  # noqa: BLE001
            json_response(self, 400, {"error": str(exc)})
