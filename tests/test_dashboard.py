import json
from pathlib import Path
from http.server import HTTPServer
import threading
import urllib.request
import urllib.parse
from src.dashboard.server import DashboardHTTPHandler
import src.dashboard.server as server_module


def test_dashboard_api(tmp_path):
    original_state_file = server_module.STATE_FILE
    temp_state = tmp_path / "project_state.json"
    temp_state.write_text(original_state_file.read_text(encoding="utf-8"), encoding="utf-8")
    server_module.STATE_FILE = temp_state

    # Setup test server on an ephemeral port
    server = HTTPServer(("127.0.0.1", 0), DashboardHTTPHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()

    try:
        # 1. Test GET /api/state
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/state")
        with urllib.request.urlopen(req) as resp:
            assert resp.status == 200
            data = json.loads(resp.read().decode("utf-8"))
            assert data["project_name"] == "LLMTradingV2"
            assert "phases" in data

        # 2. Test POST /api/note
        note_payload = json.dumps({
            "topic": "Test Note",
            "summary": "This is an automated test note."
        }).encode("utf-8")
        req_post = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/note",
            data=note_payload,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_post) as resp_post:
            assert resp_post.status == 201
            post_data = json.loads(resp_post.read().decode("utf-8"))
            assert post_data["success"] is True
            assert post_data["note"]["topic"] == "Test Note"

        # 3. Test GET /api/kage-bunshin/history
        req_kb = urllib.request.Request(f"http://127.0.0.1:{port}/api/kage-bunshin/history")
        with urllib.request.urlopen(req_kb) as resp_kb:
            assert resp_kb.status == 200
            kb_data = json.loads(resp_kb.read().decode("utf-8"))
            assert "tournaments" in kb_data
            assert len(kb_data["tournaments"]) >= 1
    finally:
        server.shutdown()
        server.server_close()
        server_module.STATE_FILE = original_state_file
