"""Database schema definition, connection management, and query helpers."""

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional
from src.config import DB_PATH

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sales_transactions (
    transaction_id TEXT PRIMARY KEY,
    order_date_raw TEXT NOT NULL,
    order_date TEXT,                   -- Stored in ISO format YYYY-MM-DD (NULL if date is invalid)
    product TEXT NOT NULL,
    category TEXT NOT NULL,
    region TEXT NOT NULL,
    sales_channel TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price REAL,                   -- Can be NULL for invalid/missing records (e.g. TXN0051)
    discount_amount REAL NOT NULL DEFAULT 0.0,
    gross_amount REAL,                 -- quantity * unit_price (NULL if unit_price is NULL)
    net_amount REAL,                   -- gross_amount - discount_amount (NULL if unit_price is NULL)
    status TEXT NOT NULL,
    data_flag TEXT NOT NULL DEFAULT 'VALID', -- 'VALID', 'MISSING_UNIT_PRICE', 'ZERO_QUANTITY', 'RETURNED'
    is_valid_for_revenue INTEGER NOT NULL DEFAULT 1 -- 1 for valid revenue, 0 otherwise
);

CREATE INDEX IF NOT EXISTS idx_sales_order_date ON sales_transactions(order_date);
CREATE INDEX IF NOT EXISTS idx_sales_product ON sales_transactions(product);
CREATE INDEX IF NOT EXISTS idx_sales_region ON sales_transactions(region);
CREATE INDEX IF NOT EXISTS idx_sales_status ON sales_transactions(status);
CREATE INDEX IF NOT EXISTS idx_sales_valid_revenue ON sales_transactions(is_valid_for_revenue);

CREATE TABLE IF NOT EXISTS data_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_timestamp TEXT DEFAULT (DATETIME('now')),
    source_file TEXT NOT NULL,
    total_records INTEGER NOT NULL,
    valid_revenue_records INTEGER NOT NULL,
    flagged_records INTEGER NOT NULL,
    notes TEXT
);
"""

def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Obtain a SQLite database connection with row factory configured."""
    target_path = Path(db_path) if db_path else DB_PATH
    target_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(target_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database tables and indexes."""
    with get_db_connection(db_path) as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

def execute_read_query(
    query: str, 
    params: tuple = (), 
    db_path: Optional[Path] = None
) -> List[Dict[str, Any]]:
    """Execute a read-only query safely and return results as a list of dicts.
    
    Guarantees no state modification. Raises ValueError if non-SELECT statements are passed.
    """
    clean_query = query.strip()
    first_token = clean_query.split()[0].upper() if clean_query else ""
    if first_token not in ("SELECT", "WITH", "EXPLAIN", "PRAGMA"):
        raise ValueError(f"Security Alert: Only read operations are permitted. Rejected: '{first_token}'")

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(clean_query, params)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
