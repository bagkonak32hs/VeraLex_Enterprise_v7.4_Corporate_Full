# db.py  — minimal ve dayanıklı SQLite katmanı
from pathlib import Path
import sqlite3, threading

BASE = Path(__file__).parent
DATA = BASE / "data"
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "veralex.db"

_lock = threading.RLock()

def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    # timeout: olası OneDrive/gecikme kilitlerini tolere etsin
    return sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)

def exec(sql, params=()):
    with _lock, connect() as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute(sql, params)
        c.commit()

def q(sql, params=()):
    with _lock, connect() as c:
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        cur = c.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

def init():
    # Ana tablolar — yoksa oluştur
    with _lock, connect() as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          username TEXT UNIQUE NOT NULL,
          pass_hash TEXT NOT NULL,
          role TEXT NOT NULL DEFAULT 'operatör',
          active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS clients(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT, national_id TEXT, phone TEXT, email TEXT, address TEXT,
          poa_no TEXT, poa_date TEXT, poa_baro TEXT, poa_attorney TEXT,
          notes TEXT
        );

        CREATE TABLE IF NOT EXISTS debtors(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT, national_id TEXT, phone TEXT, email TEXT, address TEXT,
          notes TEXT
        );

        CREATE TABLE IF NOT EXISTS cases(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_type TEXT,
          client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
          debtor_id INTEGER REFERENCES debtors(id) ON DELETE SET NULL,
          file_no TEXT, court TEXT, status TEXT,
          opened_at TEXT, drop_date TEXT,
          notes TEXT
        );

        CREATE TABLE IF NOT EXISTS dict_receivable_types(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT
        );

        CREATE TABLE IF NOT EXISTS dict_expense_types(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT
        );

        CREATE TABLE IF NOT EXISTS receivables(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          rtype_id INTEGER REFERENCES dict_receivable_types(id),
          item TEXT, amount REAL DEFAULT 0, currency TEXT DEFAULT 'TRY',
          note TEXT
        );

        CREATE TABLE IF NOT EXISTS expenses(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
          etype_id INTEGER REFERENCES dict_expense_types(id),
          amount REAL DEFAULT 0, date TEXT, note TEXT
        );

        CREATE TABLE IF NOT EXISTS reminders(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          case_id INTEGER REFERENCES cases(id) ON DELETE SET NULL,
          title TEXT, due_date TEXT, priority TEXT, note TEXT,
          done INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS audit(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          at TEXT, user TEXT, action TEXT, detail TEXT
        );

        CREATE TABLE IF NOT EXISTS trash(
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          tname TEXT NOT NULL, payload TEXT NOT NULL,
          deleted_at TEXT, user TEXT
        );
        """)
        # Sözlük tablolarına örnek türler
        c.execute("INSERT OR IGNORE INTO dict_receivable_types(id,name) VALUES (1,'Asıl Alacak')")
        c.execute("INSERT OR IGNORE INTO dict_expense_types(id,name)    VALUES (1,'Harç')")
        c.commit()
