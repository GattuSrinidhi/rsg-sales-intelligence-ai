"""Unit tests for database initialization, schema integrity, defensive validation, and idempotent CSV import."""

import csv
import logging
import pytest
from src.db import init_db, get_db_connection, execute_read_query
from src.import_data import import_sales_data, parse_row
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
    assert result["duplicate_ids_count"] == 0

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
    results = execute_read_query("SELECT COUNT(*) as count FROM sales_transactions;", db_path=populated_db)
    assert results[0]["count"] == 51

    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("DROP TABLE sales_transactions;", db_path=populated_db)

    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("DELETE FROM sales_transactions;", db_path=populated_db)

    with pytest.raises(ValueError, match="Security Alert"):
        execute_read_query("INSERT INTO sales_transactions VALUES ('1');", db_path=populated_db)

# --- New Defensive Hardening Tests ---

def test_defensive_invalid_date_handling():
    """Verify that malformed or impossible dates are preserved raw, have NULL ISO date, and are flagged."""
    row = {
        "Transaction_Id": "TXN_BAD_DATE",
        "Order_date": "32-13-2026",
        "Product": "Monitor",
        "Category": "Electronics",
        "Region": "North",
        "Sales_channel": "Online",
        "Quantity": "2",
        "Unit_price": "9500",
        "Discount_amount": "0",
        "Status": "Completed",
    }
    parsed = parse_row(row)
    assert parsed["order_date_raw"] == "32-13-2026"
    assert parsed["order_date"] is None
    assert parsed["data_flag"] == "INVALID_DATE"
    assert parsed["is_valid_for_revenue"] == 0

def test_defensive_negative_quantity_handling():
    """Verify that negative quantity records are flagged and excluded from revenue."""
    row = {
        "Transaction_Id": "TXN_NEG_QTY",
        "Order_date": "10-01-2026",
        "Product": "Mouse",
        "Category": "Accessories",
        "Region": "South",
        "Sales_channel": "Retail",
        "Quantity": "-5",
        "Unit_price": "650",
        "Discount_amount": "0",
        "Status": "Completed",
    }
    parsed = parse_row(row)
    assert parsed["quantity"] == -5
    assert parsed["data_flag"] == "NEGATIVE_VALUE"
    assert parsed["is_valid_for_revenue"] == 0

def test_defensive_negative_price_and_discount():
    """Verify that negative unit prices or discounts are flagged and excluded."""
    # Negative price
    row_neg_price = {
        "Transaction_Id": "TXN_NEG_PRICE",
        "Order_date": "10-01-2026",
        "Product": "Mouse",
        "Category": "Accessories",
        "Region": "South",
        "Sales_channel": "Retail",
        "Quantity": "5",
        "Unit_price": "-650",
        "Discount_amount": "0",
        "Status": "Completed",
    }
    parsed_price = parse_row(row_neg_price)
    assert parsed_price["data_flag"] == "NEGATIVE_VALUE"
    assert parsed_price["is_valid_for_revenue"] == 0

    # Negative discount
    row_neg_disc = {
        "Transaction_Id": "TXN_NEG_DISC",
        "Order_date": "10-01-2026",
        "Product": "Mouse",
        "Category": "Accessories",
        "Region": "South",
        "Sales_channel": "Retail",
        "Quantity": "5",
        "Unit_price": "650",
        "Discount_amount": "-100",
        "Status": "Completed",
    }
    parsed_disc = parse_row(row_neg_disc)
    assert parsed_disc["data_flag"] == "NEGATIVE_VALUE"
    assert parsed_disc["is_valid_for_revenue"] == 0

def test_defensive_discount_exceeds_gross():
    """Verify that transactions where discount exceeds gross value are flagged and excluded from revenue."""
    row = {
        "Transaction_Id": "TXN_EXCESS_DISC",
        "Order_date": "15-02-2026",
        "Product": "Keyboard",
        "Category": "Accessories",
        "Region": "East",
        "Sales_channel": "Online",
        "Quantity": "2",
        "Unit_price": "900",       # Gross = 1800
        "Discount_amount": "2500",  # Discount exceeds gross by 700
        "Status": "Completed",
    }
    parsed = parse_row(row)
    assert parsed["data_flag"] == "DISCOUNT_EXCEEDS_GROSS"
    assert parsed["is_valid_for_revenue"] == 0
    assert parsed["gross_amount"] == 1800.0
    assert parsed["net_amount"] == -700.0

def test_defensive_in_csv_duplicate_id_warning(tmp_path, caplog):
    """Verify that duplicate transaction IDs within a single CSV log a warning and deduplicate safely."""
    test_csv = tmp_path / "dup_test.csv"
    test_db = tmp_path / "dup_test.db"
    
    with open(test_csv, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Transaction_Id", "Order_date", "Product", "Category", "Region", "Sales_channel", "Quantity", "Unit_price", "Discount_amount", "Status"])
        writer.writerow(["TXN_DUP", "01-01-2026", "Mouse", "Accessories", "North", "Online", "10", "500", "0", "Completed"])
        writer.writerow(["TXN_DUP", "02-01-2026", "Mouse", "Accessories", "North", "Online", "12", "500", "0", "Completed"])

    with caplog.at_level(logging.WARNING):
        result = import_sales_data(csv_path=test_csv, db_path=test_db)

    assert result["duplicate_ids_count"] == 1
    assert "Duplicate transaction ID detected within source CSV: 'TXN_DUP'" in caplog.text

    # The database must have exactly 1 record due to primary key deduplication
    with get_db_connection(test_db) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) AS cnt, quantity FROM sales_transactions WHERE transaction_id = 'TXN_DUP';")
        row = cursor.fetchone()
        assert row["cnt"] == 1
        assert row["quantity"] == 12  # Replaced with latest row
