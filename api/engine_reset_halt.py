"""POST /api/engine_reset_halt — clear hard halt (Bearer CRON_SECRET). Body: actor."""

from http.server import BaseHTTPRequestHandler
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from actions import reset_hard_halt
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
            actor = str(body.get("actor") or "")
            engine = str(body.get("engine") or "swing")
            result = reset_hard_halt(actor, engine=engine)
            json_response(self, 200, result)
        except Exception as exc:  # noqa: BLE001
            json_response(self, 400, {"error": str(exc)})
