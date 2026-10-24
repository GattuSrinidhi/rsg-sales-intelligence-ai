"""Idempotent CSV ingestion module with data validation, sanitization, defensive hardening, and audit logging."""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import get_csv_path, DB_PATH, DATE_INPUT_FORMAT, DATE_DB_FORMAT
from src.db import get_db_connection, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

def parse_row(row: Dict[str, str]) -> Dict[str, Any]:
    """Clean, sanitize, validate, and classify an individual CSV transaction row based on business rules."""
    cleaned = {k.strip(): v.strip() if isinstance(v, str) else v for k, v in row.items()}
    
    txn_id = cleaned.get("Transaction_Id", "")
    order_date_raw = cleaned.get("Order_date", "")
    product = cleaned.get("Product", "")
    category = cleaned.get("Category", "")
    region = cleaned.get("Region", "")
    sales_channel = cleaned.get("Sales_channel", "")
    status = cleaned.get("Status", "")
    
    # 1. Date Validation: Standardize order date to ISO YYYY-MM-DD
    order_date_iso: Optional[str] = None
    is_date_valid = True
    if order_date_raw:
        try:
            dt = datetime.strptime(order_date_raw, DATE_INPUT_FORMAT)
            order_date_iso = dt.strftime(DATE_DB_FORMAT)
        except ValueError as err:
            logger.warning(f"Invalid date format for {txn_id}: '{order_date_raw}' ({err})")
            is_date_valid = False
            order_date_iso = None
    else:
        is_date_valid = False
        order_date_iso = None

    # 2. Parse numeric fields safely
    quantity_str = cleaned.get("Quantity", "0")
    unit_price_str = cleaned.get("Unit_price", "")
    discount_str = cleaned.get("Discount_amount", "0")
    
    try:
        quantity = int(quantity_str) if quantity_str else 0
    except ValueError:
        quantity = 0

    try:
        discount = float(discount_str) if discount_str else 0.0
    except ValueError:
        discount = 0.0

    unit_price: Optional[float] = None
    if unit_price_str:
        try:
            unit_price = float(unit_price_str)
        except ValueError:
            unit_price = None

    # 3. Apply Explicit Business Rules with Defensive Priority
    gross_amount: Optional[float] = None
    net_amount: Optional[float] = None
    data_flag = "VALID"
    is_valid_for_revenue = 1

    if not txn_id:
        # Rule: Missing Transaction ID is invalid
        data_flag = "MISSING_TRANSACTION_ID"
        is_valid_for_revenue = 0
    elif not is_date_valid:
        # Rule: Malformed or impossible dates must be flagged and excluded from revenue analytics
        data_flag = "INVALID_DATE"
        is_valid_for_revenue = 0
        if unit_price is not None:
            gross_amount = round(quantity * unit_price, 2)
            net_amount = round(gross_amount - discount, 2)
    elif unit_price is None:
        # Rule: Missing monetary value must be retained, flagged, and excluded from revenue sums
        data_flag = "MISSING_UNIT_PRICE"
        is_valid_for_revenue = 0
        gross_amount = None
        net_amount = None
    elif quantity < 0 or unit_price < 0 or discount < 0:
        # Rule: Negative monetary or quantity values are invalid for revenue
        data_flag = "NEGATIVE_VALUE"
        is_valid_for_revenue = 0
        gross_amount = round(quantity * unit_price, 2)
        net_amount = round(gross_amount - discount, 2)
    elif (quantity * unit_price) < discount:
        # Rule: Discounts exceeding gross value are invalid (do not report negative net sales)
        data_flag = "DISCOUNT_EXCEEDS_GROSS"
        is_valid_for_revenue = 0
        gross_amount = round(quantity * unit_price, 2)
        net_amount = round(gross_amount - discount, 2)
    elif status.strip().lower() in ("returned", "cancelled"):
        # Rule: Returned transactions cannot count towards top-line earned revenue
        data_flag = "RETURNED_TRANSACTION"
        is_valid_for_revenue = 0
        gross_amount = round(quantity * unit_price, 2)
        net_amount = round(gross_amount - discount, 2)
    elif quantity == 0:
        # Rule: Zero quantity transactions are valid audits but contribute zero revenue
        data_flag = "ZERO_QUANTITY"
        is_valid_for_revenue = 1
        gross_amount = 0.0
        net_amount = 0.0
    else:
        # Standard completed transaction
        gross_amount = round(quantity * unit_price, 2)
        net_amount = round(gross_amount - discount, 2)
        data_flag = "VALID"
        is_valid_for_revenue = 1

    return {
        "transaction_id": txn_id,
        "order_date_raw": order_date_raw,
        "order_date": order_date_iso,
        "product": product,
        "category": category,
        "region": region,
        "sales_channel": sales_channel,
        "quantity": quantity,
        "unit_price": unit_price,
        "discount_amount": discount,
        "gross_amount": gross_amount,
        "net_amount": net_amount,
        "status": status,
        "data_flag": data_flag,
        "is_valid_for_revenue": is_valid_for_revenue,
    }

def import_sales_data(
    csv_path: Optional[Path] = None, 
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Ingest CSV data into SQLite idempotently and log data quality metrics."""
    source_file = csv_path or get_csv_path()
    if not Path(source_file).exists():
        raise FileNotFoundError(f"Source CSV not found: {source_file}")

    init_db(db_path)
    
    rows_to_insert = []
    seen_ids = set()
    duplicate_ids_count = 0

    with open(source_file, mode="r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for raw_row in reader:
            tid = raw_row.get("Transaction_Id", "").strip()
            if tid:
                if tid in seen_ids:
                    logger.warning(f"Duplicate transaction ID detected within source CSV: '{tid}'")
                    duplicate_ids_count += 1
                seen_ids.add(tid)
            parsed = parse_row(raw_row)
            rows_to_insert.append(parsed)

    total_records = len(rows_to_insert)
    valid_revenue_records = sum(1 for r in rows_to_insert if r["is_valid_for_revenue"] == 1)
    flagged_records = total_records - valid_revenue_records

    insert_sql = """
    INSERT OR REPLACE INTO sales_transactions (
        transaction_id, order_date_raw, order_date, product, category,
        region, sales_channel, quantity, unit_price, discount_amount,
        gross_amount, net_amount, status, data_flag, is_valid_for_revenue
    ) VALUES (
        :transaction_id, :order_date_raw, :order_date, :product, :category,
        :region, :sales_channel, :quantity, :unit_price, :discount_amount,
        :gross_amount, :net_amount, :status, :data_flag, :is_valid_for_revenue
    );
    """

    audit_sql = """
    INSERT INTO data_audit_log (
        source_file, total_records, valid_revenue_records, flagged_records, notes
    ) VALUES (?, ?, ?, ?, ?);
    """

    notes = (
        f"Import completed. Total: {total_records}, "
        f"Valid for Revenue: {valid_revenue_records}, "
        f"Flagged (Excluded): {flagged_records}."
    )
    if duplicate_ids_count > 0:
        notes += f" Detected {duplicate_ids_count} duplicate transaction IDs in file."

    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany(insert_sql, rows_to_insert)
        cursor.execute(audit_sql, (str(source_file), total_records, valid_revenue_records, flagged_records, notes))
        conn.commit()

    logger.info(notes)
    return {
        "status": "success",
        "total_records": total_records,
        "valid_revenue_records": valid_revenue_records,
        "flagged_records": flagged_records,
        "duplicate_ids_count": duplicate_ids_count,
        "source_file": str(source_file),
    }

if __name__ == "__main__":
    result = import_sales_data()
    print("Ingestion Result:", result)
