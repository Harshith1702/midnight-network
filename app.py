import os, threading, time
from flask import Flask, jsonify, request
import db, monitor

def _inc(r):
    d = dict(r)
    if d["duration_s"] is None:
        d["duration_s"] = time.time() - d["started_at"]
        d["open"] = True
    return d

def create_app(start=True):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    db.init()
    if start and os.environ.get("DISABLE_SCHEDULER") != "1":
        threading.Thread(target=monitor.loop, daemon=True).start()

    @app.get("/")
    def index():
        return app.send_static_file("index.html")

    @app.get("/health")
    def health():
        return jsonify(status="ok", time=time.time())

    @app.get("/api/summary")
    def summary():
        c = db.conn()
        n = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM services GROUP BY status")}
        inc = c.execute("SELECT i.*, s.name FROM incidents i JOIN services s ON s.id=i.service_id "
                        "ORDER BY i.started_at DESC LIMIT 15").fetchall()
        out = dict(total=sum(n.values()), up=n.get("UP", 0), down=n.get("DOWN", 0),
                   unknown=n.get("UNKNOWN", 0), incidents=[_inc(r) for r in inc])
        c.close()
        return jsonify(out)

    @app.get("/api/services")
    def services():
        c = db.conn()
        out = []
        for r in c.execute("SELECT * FROM services ORDER BY id"):
            d = dict(r)
            h = c.execute("SELECT ts,is_up,response_ms FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 30",
                          (r["id"],)).fetchall()[::-1]
            d.update(uptime=monitor.uptime(c, r["id"]), history=[dict(x) for x in h],
                     last_ms=h[-1]["response_ms"] if h else None)
            out.append(d)
        c.close()
        return jsonify(out)

    @app.post("/api/services")
    def add():
        j = request.get_json(silent=True) or {}
        name = str(j.get("name", "")).strip()
        try:
            interval = int(j.get("interval", 60))
        except (TypeError, ValueError):
            return jsonify(error="Interval must be a number of seconds"), 400
        lo = int(os.environ.get("MIN_INTERVAL", 10))
        if not name or len(name) > 80:
            return jsonify(error="Name is required (max 80 characters)"), 400
        if not lo <= interval <= 86400:
            return jsonify(error=f"Interval must be between {lo} and 86400 seconds"), 400
        try:
            url = monitor.validate_url(j.get("url", ""))
        except ValueError as e:
            return jsonify(error=str(e)), 400
        c = db.conn()
        with c:
            cur = c.execute("INSERT INTO services(name,url,interval_s,created_at) VALUES(?,?,?,?)",
                            (name, url, interval, time.time()))
        c.close()
        return jsonify(id=cur.lastrowid), 201

    @app.post("/api/services/<int:sid>/toggle")
    def toggle(sid):
        c = db.conn()
        with c:
            c.execute("UPDATE services SET active=1-active WHERE id=?", (sid,))
        c.close()
        return jsonify(ok=True)

    @app.post("/api/services/<int:sid>/check")
    def check_now(sid):
        c = db.conn()
        s = c.execute("SELECT url FROM services WHERE id=?", (sid,)).fetchone()
        c.close()
        if not s:
            return jsonify(error="Not found"), 404
        res = monitor.check(s["url"])
        monitor.record(sid, res)
        return jsonify(res)

    @app.delete("/api/services/<int:sid>")
    def delete(sid):
        c = db.conn()
        with c:
            c.execute("DELETE FROM services WHERE id=?", (sid,))
        c.close()
        return jsonify(ok=True)

    @app.get("/api/services/<int:sid>")
    def detail(sid):
        c = db.conn()
        s = c.execute("SELECT * FROM services WHERE id=?", (sid,)).fetchone()
        if not s:
            c.close()
            return jsonify(error="Not found"), 404
        checks = [dict(r) for r in c.execute("SELECT * FROM checks WHERE service_id=? ORDER BY id DESC LIMIT 50", (sid,))]
        inc = [_inc(r) for r in c.execute("SELECT * FROM incidents WHERE service_id=? ORDER BY started_at DESC LIMIT 20", (sid,))]
        changes = []
        for i in inc:
            changes.append(dict(ts=i["started_at"], to="DOWN", error=i["error"]))
            if i["ended_at"]:
                changes.append(dict(ts=i["ended_at"], to="UP", error=None))
        changes.sort(key=lambda x: -x["ts"])
        out = dict(service=dict(s), uptime=monitor.uptime(c, sid), checks=checks, incidents=inc, changes=changes)
        c.close()
        return jsonify(out)

    return app

if __name__ == "__main__":
    create_app().run(host=os.environ.get("HOST", "127.0.0.1"), port=int(os.environ.get("PORT", 8000)))
