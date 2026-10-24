"""Unit tests for database initialization, schema integrity, and idempotent CSV import."""

import pytest
from src.db import init_db, get_db_connection, execute_read_query
from src.import_data import import_sales_data
from src.config import CSV_PRIMARY_PATH, CSV_FALLBACK_PATH

def get_test_csv():
    return CSV_PRIMARY_PATH if CSV_PRIMARY_PATH.exists() else CSV_FALLBACK_PATH

def test_schema_initialization(temp_db_path):
    """Test that all tables and indexes are created properly."""
    with get_db_connection(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "sales_transactions" in tables
        assert "data_audit_log" in tables

def test_import_sales_data(temp_db_path):
    """Test standard ingestion of the official CSV dataset."""
    result = import_sales_data(csv_path=get_test_csv(), db_path=temp_db_path)
    assert result["status"] == "success"
    assert result["total_records"] == 51
    assert result["valid_revenue_records"] == 49
    assert result["flagged_records"] == 2

    # Verify counts directly in the database
    with get_db_connection(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM sales_transactions;")
        assert cursor.fetchone()["cnt"] == 51

        cursor.execute("SELECT COUNT(*) AS cnt FROM sales_transactions WHERE is_valid_for_revenue = 1;")
        assert cursor.fetchone()["cnt"] == 49

        cursor.execute("SELECT COUNT(*) AS cnt FROM sales_transactions WHERE is_valid_for_revenue = 0;")
        assert cursor.fetchone()["cnt"] == 2

def test_edge_case_missing_unit_price(populated_db):
    """Verify that TXN0051 is safely stored with NULL price and excluded from revenue."""
    rows = execute_read_query(
        "SELECT * FROM sales_transactions WHERE transaction_id = 'TXN0051';",
        db_path=populated_db
    )
    assert len(rows) == 1
    record = rows[0]
    assert record["unit_price"] is None
    assert record["gross_amount"] is None
    assert record["net_amount"] is None
    assert record["data_flag"] == "MISSING_UNIT_PRICE"
    assert record["is_valid_for_revenue"] == 0

def test_edge_case_returned_transaction(populated_db):
    """Verify that TXN0033 (Returned status) is excluded from revenue sums."""
    rows = execute_read_query(
        "SELECT * FROM sales_transactions WHERE transaction_id = 'TXN0033';",
        db_path=populated_db
    )
    assert len(rows) == 1
    record = rows[0]
    assert record["status"] == "Returned"
    assert record["data_flag"] == "RETURNED_TRANSACTION"
    assert record["is_valid_for_revenue"] == 0
    assert record["gross_amount"] == 19000.0  # 2 * 9500

def test_edge_case_zero_quantity(populated_db):
    """Verify that TXN0034 (Quantity = 0) is flagged and yields zero revenue."""
    rows = execute_read_query(
        "SELECT * FROM sales_transactions WHERE transaction_id = 'TXN0034';",
        db_path=populated_db
    )
    assert len(rows) == 1
    record = rows[0]
    assert record["quantity"] == 0
    assert record["gross_amount"] == 0.0
    assert record["net_amount"] == 0.0
    assert record["data_flag"] == "ZERO_QUANTITY"
    assert record["is_valid_for_revenue"] == 1

def test_import_idempotency(temp_db_path):
    """Verify that running import_sales_data multiple times does not produce duplicate rows."""
    csv_file = get_test_csv()
    import_sales_data(csv_path=csv_file, db_path=temp_db_path)
    import_sales_data(csv_path=csv_file, db_path=temp_db_path)
    import_sales_data(csv_path=csv_file, db_path=temp_db_path)

    with get_db_connection(temp_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt FROM sales_transactions;")
        assert cursor.fetchone()["cnt"] == 51

def test_execute_read_query_security(populated_db):
    """Verify that execute_read_query permits SELECT and strictly rejects write/destructive statements."""
    # Permitted
    results = execute_read_query("SELECT COUNT(*) as count FROM sales_transactions;", db_path=populated_db)
    assert results[0]["count"] == 51

    # Rejected destructive attempts
    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("DROP TABLE sales_transactions;", db_path=populated_db)

    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("DELETE FROM sales_transactions;", db_path=populated_db)

    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("INSERT INTO sales_transactions VALUES ('1');", db_path=populated_db)
