import sqlite3

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    ssn TEXT NOT NULL,            -- PLANTED:V9:db
    account_number TEXT NOT NULL,
    amount REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'received'
);
CREATE VIEW IF NOT EXISTS v_uw_export AS
    SELECT a.id AS application_id, c.name AS applicant,
           substr(a.ssn, -4) AS tin_last4, substr(a.account_number, -4) AS acct_last4, a.amount AS amount
    FROM applications a JOIN customers c ON c.id = a.customer_id;
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.path("lendwise.db"))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
