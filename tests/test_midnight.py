import sys, os, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import pytest, db, monitor
from app import create_app

STATE = {"code": 200}

class H(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(STATE["code"]); self.end_headers()
    def log_message(self, *a): pass

@pytest.fixture
def target(monkeypatch):
    monkeypatch.setenv("ALLOW_PRIVATE_TARGETS", "true")
    STATE["code"] = 200
    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/"
    srv.shutdown()

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("ALLOW_PRIVATE_TARGETS", "true")
    monkeypatch.setenv("DISABLE_SCHEDULER", "1")
    return create_app(start=False).test_client()

def add(client, url):
    r = client.post("/api/services", json={"name": "t", "url": url, "interval": 30})
    assert r.status_code == 201
    return r.get_json()["id"]

def test_health_endpoint(client):
    assert client.get("/health").get_json()["status"] == "ok"

def test_check_up_records_status_and_time(target):
    r = monitor.check(target)
    assert r["is_up"] and r["status_code"] == 200 and r["response_ms"] >= 0

def test_check_http_error_and_connection_failure(target):
    STATE["code"] = 503
    r = monitor.check(target)
    assert not r["is_up"] and r["status_code"] == 503
    r = monitor.check("http://127.0.0.1:1/", timeout=1)
    assert not r["is_up"] and r["status_code"] is None and r["error"]

def test_incident_created_and_recovered(client, target):
    sid = add(client, target)
    client.post(f"/api/services/{sid}/check")
    STATE["code"] = 500
    client.post(f"/api/services/{sid}/check")
    client.post(f"/api/services/{sid}/check")  # still down: no second incident
    d = client.get(f"/api/services/{sid}").get_json()
    assert len(d["incidents"]) == 1 and d["incidents"][0].get("open")
    time.sleep(0.05)
    STATE["code"] = 200
    client.post(f"/api/services/{sid}/check")
    d = client.get(f"/api/services/{sid}").get_json()
    inc = d["incidents"][0]
    assert d["service"]["status"] == "UP" and inc["ended_at"] and inc["duration_s"] > 0

def test_uptime_calculation(client, target):
    sid = add(client, target)
    for code in (200, 200, 500, 200):
        STATE["code"] = code
        client.post(f"/api/services/{sid}/check")
    assert client.get(f"/api/services/{sid}").get_json()["uptime"] == 75.0

def test_uptime_none_without_checks(client, target):
    sid = add(client, target)
    c = db.conn()
    assert monitor.uptime(c, sid) is None

def test_data_survives_restart(client, target):
    sid = add(client, target)
    client.post(f"/api/services/{sid}/check")
    db.init()  # simulates a restart against the same file
    assert len(client.get("/api/services").get_json()) == 1
    assert client.get(f"/api/services/{sid}").get_json()["checks"]

@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://localhost/", "http://169.254.169.254/latest/", "http://10.0.0.5/", "http://[::1]/"])
def test_private_targets_blocked(monkeypatch, url):
    monkeypatch.setenv("ALLOW_PRIVATE_TARGETS", "false")
    with pytest.raises(ValueError):
        monitor.validate_url(url)

@pytest.mark.parametrize("url", ["ftp://example.com", "notaurl", "", "http://"])
def test_invalid_urls_rejected(client, url):
    assert client.post("/api/services", json={"name": "x", "url": url}).status_code == 400
