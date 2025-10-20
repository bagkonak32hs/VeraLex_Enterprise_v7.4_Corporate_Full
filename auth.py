
from pathlib import Path
from utils import ensure_data_dir, get_data_dir
import sqlite3, hashlib

BASE = Path(__file__).parent
DB = get_data_dir() / "mip.db"

def connect():
    ensure_data_dir()
    return sqlite3.connect(DB)

def pass_hash(s): 
    return hashlib.sha256(("salt::" + s).encode("utf-8")).hexdigest()

def ensure_first_user(conn):
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    n = cur.fetchone()[0]
    if n == 0:
        # create admin without password until first login
        cur.execute("INSERT INTO users(username, pass_hash, role, active) VALUES (?,?,?,1)",
                    ("admin", "TO_BE_SET", "admin"))
        conn.commit()

def check_login(username, password):
    with connect() as c:
        row = c.execute("SELECT id, pass_hash, role, active FROM users WHERE username=?", (username,)).fetchone()
        if not row:
            return None
        uid, ph, role, active = row
        if not active:
            return None
        if ph == "TO_BE_SET":
            # set now
            c.execute("UPDATE users SET pass_hash=? WHERE id=?", (pass_hash(password), uid))
            c.commit()
            return (username, role)
        ok = (ph == pass_hash(password))
        return (username, role) if ok else None
