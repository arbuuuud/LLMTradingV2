import json
import os
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse
from datetime import datetime

STATE_FILE = Path("data/project_state.json")
CACHE_FILE = Path("data/cache/live_snapshot_xauusd.json")
HTML_FILE = Path("src/dashboard/index.html")


class DashboardHTTPHandler(BaseHTTPRequestHandler):
    def _set_json_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _set_html_headers(self, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_json_headers(204)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            if HTML_FILE.exists():
                content = HTML_FILE.read_bytes()
                self._set_html_headers(200)
                self.wfile.write(content)
            else:
                self.send_error(404, "Dashboard HTML not found")
        elif path == "/api/state":
            if STATE_FILE.exists():
                data = STATE_FILE.read_text(encoding="utf-8")
                self._set_json_headers(200)
                self.wfile.write(data.encode("utf-8"))
            else:
                self._set_json_headers(200)
                self.wfile.write(json.dumps({"error": "State file not initialized"}).encode("utf-8"))
        elif path == "/api/snapshot":
            if CACHE_FILE.exists():
                data = CACHE_FILE.read_text(encoding="utf-8")
                self._set_json_headers(200)
                self.wfile.write(data.encode("utf-8"))
            else:
                self._set_json_headers(200)
                self.wfile.write(json.dumps({"status": "NO_ACTIVE_SNAPSHOT", "message": "Run live feed generator to emit snapshot"}).encode("utf-8"))
        else:
            self.send_error(404, "Endpoint not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/note":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                payload = json.loads(body)
                if STATE_FILE.exists():
                    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
                else:
                    state = {"decisions_and_notes": []}

                new_note = {
                    "id": f"DEC-{len(state.get('decisions_and_notes', [])) + 1:03d}",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "topic": payload.get("topic", "General Note"),
                    "summary": payload.get("summary", ""),
                    "status": "CONFIRMED"
                }

                state.setdefault("decisions_and_notes", []).append(new_note)
                STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

                self._set_json_headers(201)
                self.wfile.write(json.dumps({"success": True, "note": new_note}).encode("utf-8"))
            except Exception as e:
                self._set_json_headers(400)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_error(404, "Endpoint not found")

    def log_message(self, format, *args):
        # Clean logging
        pass


def run_dashboard_server(host: str = "127.0.0.1", port: int = 8080):
    server_address = (host, port)
    httpd = HTTPServer(server_address, DashboardHTTPHandler)
    print(f"🚀 LLMTradingV2 Project Management Dashboard is running on http://{host}:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDashboard server stopped.")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    run_dashboard_server()
