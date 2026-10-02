import os, sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS services(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, url TEXT NOT NULL,
  interval_s INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'UNKNOWN', last_check REAL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS checks(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  ts REAL NOT NULL, status_code INTEGER, response_ms REAL, is_up INTEGER NOT NULL, error TEXT);
CREATE TABLE IF NOT EXISTS incidents(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  service_id INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
  started_at REAL NOT NULL, ended_at REAL, duration_s REAL, error TEXT);
CREATE INDEX IF NOT EXISTS idx_checks ON checks(service_id, id);
CREATE INDEX IF NOT EXISTS idx_inc ON incidents(service_id, started_at);
"""

def conn():
    p = os.environ.get("DB_PATH", "data/midnight.db")
    if os.path.dirname(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    c = sqlite3.connect(p, timeout=10)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    return c

def init():
    c = conn()
    with c:
        c.executescript(SCHEMA)
    c.close()
