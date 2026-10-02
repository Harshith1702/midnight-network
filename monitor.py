import ipaddress, logging, os, socket, threading, time
from urllib.parse import urlparse
import requests
import db

log = logging.getLogger("midnight")
_busy, _lock = set(), threading.Lock()

def validate_url(url):
    """Reject non-http(s) URLs and hosts resolving to private/reserved addresses."""
    url = (url or "").strip()
    u = urlparse(url)
    if u.scheme not in ("http", "https") or not u.hostname:
        raise ValueError("URL must start with http:// or https:// and include a host")
    if os.environ.get("ALLOW_PRIVATE_TARGETS", "false").lower() == "true":
        return url
    try:
        infos = socket.getaddrinfo(u.hostname, u.port or 80, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        raise ValueError("Host does not resolve")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        ip = getattr(ip, "ipv4_mapped", None) or ip
        if not ip.is_global:
            raise ValueError("Target resolves to a private or reserved address")
    return url

def check(url, timeout=None):
    """One HTTP check. Returns a result dict; never raises."""
    timeout = timeout or float(os.environ.get("CHECK_TIMEOUT", 5))
    t = time.time()
    try:
        validate_url(url)
        r = requests.get(url, timeout=timeout, allow_redirects=False, stream=True,
                         headers={"User-Agent": "MidnightNetwork/1.0"})
        ms, code = round((time.time() - t) * 1000, 1), r.status_code
        r.close()
        up = code < 400
        return dict(ts=t, status_code=code, response_ms=ms, is_up=up, error=None if up else f"HTTP {code}")
    except ValueError as e:
        err = str(e)
    except requests.Timeout:
        err = "Timed out"
    except requests.RequestException:
        err = "Connection failed"
    return dict(ts=t, status_code=None, response_ms=None, is_up=False, error=err)

def record(sid, res):
    """Store a check and open/close incidents on status transitions."""
    c = db.conn()
    with c:
        s = c.execute("SELECT status FROM services WHERE id=?", (sid,)).fetchone()
        if not s:
            return
        c.execute("INSERT INTO checks(service_id,ts,status_code,response_ms,is_up,error) VALUES(?,?,?,?,?,?)",
                  (sid, res["ts"], res["status_code"], res["response_ms"], int(res["is_up"]), res["error"]))
        new = "UP" if res["is_up"] else "DOWN"
        if new == "DOWN" and s["status"] != "DOWN":
            c.execute("INSERT INTO incidents(service_id,started_at,error) VALUES(?,?,?)", (sid, res["ts"], res["error"]))
        elif new == "UP" and s["status"] == "DOWN":
            c.execute("UPDATE incidents SET ended_at=?, duration_s=?-started_at WHERE service_id=? AND ended_at IS NULL",
                      (res["ts"], res["ts"], sid))
        c.execute("UPDATE services SET status=?, last_check=? WHERE id=?", (new, res["ts"], sid))
    c.close()

def uptime(c, sid):
    r = c.execute("SELECT COUNT(*) n, SUM(is_up) u FROM checks WHERE service_id=?", (sid,)).fetchone()
    return round(100.0 * r["u"] / r["n"], 2) if r["n"] else None

def _run(sid, url):
    try:
        record(sid, check(url))
    except Exception:
        log.exception("check failed for service %s", sid)
    finally:
        with _lock:
            _busy.discard(sid)

def tick():
    now = time.time()
    c = db.conn()
    rows = c.execute("SELECT id,url,interval_s,last_check FROM services WHERE active=1").fetchall()
    c.close()
    for r in rows:
        if now - (r["last_check"] or 0) >= r["interval_s"]:
            with _lock:
                if r["id"] in _busy:
                    continue
                _busy.add(r["id"])
            threading.Thread(target=_run, args=(r["id"], r["url"]), daemon=True).start()

def loop():
    while True:
        try:
            tick()
        except Exception:
            log.exception("scheduler error")
        time.sleep(1)
