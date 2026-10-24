"""Deterministic Sales Analytics Engine.

Implements pure, verifiable calculations for all official challenge business questions:
1. Total revenue (gross vs net, discount total, transaction volume).
2. Product with the highest revenue (with volume comparison and runner-ups).
3. Monthly revenue trend (chronological series with Month-over-Month absolute and percentage changes).
4. Region with the highest sales (resolving revenue vs units volume explicitly).
5. Revenue change between two specified months (chronological comparison with absolute and percentage deltas).

All calculations enforce the documented Net Revenue formula:
    Gross Revenue = Quantity * Unit Price
    Net Revenue = Gross Revenue - Discount Amount
and strictly filter records by `is_valid_for_revenue = 1`.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.config import DB_PATH
from src.db import execute_read_query

MONTH_NAMES = {
    "january": "01", "jan": "01",
    "february": "02", "feb": "02",
    "march": "03", "mar": "03",
    "april": "04", "apr": "04",
    "may": "05",
    "june": "06", "jun": "06",
    "july": "07", "jul": "07",
    "august": "08", "aug": "08",
    "september": "09", "sep": "09", "sept": "09",
    "october": "10", "oct": "10",
    "november": "11", "nov": "11",
    "december": "12", "dec": "12",
}

def normalize_month(month_str: str, default_year: str = "2026") -> str:
    """Normalize user-supplied month strings into standardized ISO 'YYYY-MM' format.
    
    Accepts: '2026-04', '2026/04', 'April', 'apr', '04', 'April 2026', '2026 April'.
    Raises ValueError on unrecognized or invalid month inputs.
    """
    cleaned = month_str.strip().lower()
    if not cleaned:
        raise ValueError("Month input cannot be empty.")

    # Match YYYY-MM or YYYY/MM
    match_iso = re.match(r"^(\d{4})[-/](\d{1,2})$", cleaned)
    if match_iso:
        year, month = match_iso.groups()
        return f"{year}-{int(month):02d}"

    # Match MM-YYYY or MM/YYYY
    match_my = re.match(r"^(\d{1,2})[-/](\d{4})$", cleaned)
    if match_my:
        month, year = match_my.groups()
        return f"{year}-{int(month):02d}"

    # Extract year if present
    year = default_year
    year_match = re.search(r"\b(20\d\d)\b", cleaned)
    if year_match:
        year = year_match.group(1)
        cleaned = re.sub(r"\b(20\d\d)\b", "", cleaned).strip()

    # Check named months
    cleaned_word = re.sub(r"[^a-z]", "", cleaned)
    if cleaned_word in MONTH_NAMES:
        return f"{year}-{MONTH_NAMES[cleaned_word]}"

    # Check numeric month string (e.g. '4' or '04')
    if cleaned.isdigit():
        m_int = int(cleaned)
        if 1 <= m_int <= 12:
            return f"{year}-{m_int:02d}"

    raise ValueError(
        f"Unrecognized month format: '{month_str}'. "
        "Expected format like '2026-04', 'April', or '04'."
    )

def get_total_revenue(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calculate total net revenue, gross revenue, discounts, and volume for valid transactions."""
    summary_sql = """
    SELECT 
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS total_net_revenue,
        COALESCE(ROUND(SUM(gross_amount), 2), 0.0) AS total_gross_revenue,
        COALESCE(ROUND(SUM(discount_amount), 2), 0.0) AS total_discount_amount,
        COALESCE(SUM(quantity), 0) AS total_units_sold,
        COUNT(*) AS valid_transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1;
    """
    summary = execute_read_query(summary_sql, db_path=db_path)[0]

    category_sql = """
    SELECT 
        category,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1
    GROUP BY category
    ORDER BY net_revenue DESC;
    """
    categories = execute_read_query(category_sql, db_path=db_path)

    channel_sql = """
    SELECT 
        sales_channel,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1
    GROUP BY sales_channel
    ORDER BY net_revenue DESC;
    """
    channels = execute_read_query(channel_sql, db_path=db_path)

    total_net = summary["total_net_revenue"]
    total_gross = summary["total_gross_revenue"]
    total_disc = summary["total_discount_amount"]
    valid_txns = summary["valid_transaction_count"]
    total_units = summary["total_units_sold"]

    narrative = (
        f"The total net revenue generated is ₹{total_net:,.2f} across {valid_txns} valid completed transactions "
        f"(Gross: ₹{total_gross:,.2f}, Total Discounts: ₹{total_disc:,.2f}, Total Units: {total_units:,})."
    )

    return {
        "metric": "total_revenue",
        "total_net_revenue": total_net,
        "total_gross_revenue": total_gross,
        "total_discount_amount": total_disc,
        "total_units_sold": total_units,
        "valid_transaction_count": valid_txns,
        "category_breakdown": categories,
        "channel_breakdown": channels,
        "formula": "Net Revenue = SUM(quantity * unit_price - discount_amount) WHERE is_valid_for_revenue = 1",
        "narrative": narrative,
    }

def get_top_product(metric: str = "revenue", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Identify product(s) generating highest revenue or volume sold.
    
    Parameters:
        metric: 'revenue' (default) for net revenue, or 'units' for quantity sold.
    """
    order_col = "net_revenue" if metric == "revenue" else "units_sold"
    
    product_sql = f"""
    SELECT 
        product,
        category,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(ROUND(SUM(gross_amount), 2), 0.0) AS gross_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1
    GROUP BY product, category
    ORDER BY {order_col} DESC, product ASC;
    """
    products = execute_read_query(product_sql, db_path=db_path)

    if not products:
        return {
            "metric": "top_product",
            "top_products": [],
            "top_value": 0.0,
            "metric_used": metric,
            "all_products": [],
            "narrative": "No sales transaction records found.",
        }

    top_val = products[0][order_col]
    # Handle ties: all products with the max value
    top_winners = [p for p in products if p[order_col] == top_val]

    winner_names = ", ".join(p["product"] for p in top_winners)
    if metric == "revenue":
        narrative = (
            f"The product generating the highest revenue is {winner_names} with "
            f"₹{top_val:,.2f} in net revenue ({products[0]['units_sold']} units sold)."
        )
    else:
        narrative = (
            f"The product generating the highest volume is {winner_names} with "
            f"{top_val:,} units sold (₹{products[0]['net_revenue']:,.2f} net revenue)."
        )

    return {
        "metric": "top_product",
        "metric_used": metric,
        "top_product": products[0]["product"] if len(top_winners) == 1 else [p["product"] for p in top_winners],
        "top_value": top_val,
        "is_tie": len(top_winners) > 1,
        "winners": top_winners,
        "ranking": products,
        "narrative": narrative,
    }

def get_monthly_revenue_trend(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Calculate chronological monthly revenue and month-over-month (MoM) deltas."""
    trend_sql = """
    SELECT 
        strftime('%Y-%m', order_date) AS month,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(ROUND(SUM(gross_amount), 2), 0.0) AS gross_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1 AND order_date IS NOT NULL
    GROUP BY month
    ORDER BY month ASC;
    """
    rows = execute_read_query(trend_sql, db_path=db_path)

    if not rows:
        return {
            "metric": "monthly_revenue_trend",
            "trend": [],
            "total_months": 0,
            "peak_month": None,
            "lowest_month": None,
            "average_monthly_revenue": 0.0,
            "narrative": "No dated sales transaction records found.",
        }

    trend_data = []
    prev_rev: Optional[float] = None

    for r in rows:
        rev = r["net_revenue"]
        if prev_rev is None:
            mom_abs = None
            mom_pct = None
        else:
            mom_abs = round(rev - prev_rev, 2)
            mom_pct = round((mom_abs / prev_rev) * 100, 2) if prev_rev > 0 else None

        trend_data.append({
            "month": r["month"],
            "net_revenue": rev,
            "gross_revenue": r["gross_revenue"],
            "units_sold": r["units_sold"],
            "transaction_count": r["transaction_count"],
            "mom_change_amount": mom_abs,
            "mom_change_percent": mom_pct,
        })
        prev_rev = rev

    peak = max(trend_data, key=lambda x: x["net_revenue"])
    lowest = min(trend_data, key=lambda x: x["net_revenue"])
    avg_rev = round(sum(d["net_revenue"] for d in trend_data) / len(trend_data), 2)

    narrative = (
        f"Monthly revenue spans {len(trend_data)} months, averaging ₹{avg_rev:,.2f}/month. "
        f"Peak revenue occurred in {peak['month']} at ₹{peak['net_revenue']:,.2f}, while the "
        f"lowest revenue occurred in {lowest['month']} at ₹{lowest['net_revenue']:,.2f}."
    )

    return {
        "metric": "monthly_revenue_trend",
        "trend": trend_data,
        "total_months": len(trend_data),
        "peak_month": peak,
        "lowest_month": lowest,
        "average_monthly_revenue": avg_rev,
        "narrative": narrative,
    }

def get_top_region(metric: str = "revenue", db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Determine the highest sales region, reporting both revenue and volume explicitly.
    
    Resolves the semantic ambiguity of 'highest sales' by computing both
    Net Revenue (₹) and Units Sold (Volume), labeling each metric clearly.
    """
    region_sql = """
    SELECT 
        region,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(ROUND(SUM(gross_amount), 2), 0.0) AS gross_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1
    GROUP BY region
    ORDER BY net_revenue DESC;
    """
    regions = execute_read_query(region_sql, db_path=db_path)

    if not regions:
        return {
            "metric": "top_region",
            "top_region_revenue": None,
            "top_region_units": None,
            "all_regions": [],
            "narrative": "No regional sales transaction records found.",
        }

    total_net = sum(r["net_revenue"] for r in regions)
    total_units = sum(r["units_sold"] for r in regions)

    # Attach percentage shares
    enriched = []
    for r in regions:
        rev_share = round((r["net_revenue"] / total_net) * 100, 2) if total_net > 0 else 0.0
        unit_share = round((r["units_sold"] / total_units) * 100, 2) if total_units > 0 else 0.0
        enriched.append({
            **r,
            "revenue_share_percent": rev_share,
            "units_share_percent": unit_share,
        })

    by_revenue = sorted(enriched, key=lambda x: x["net_revenue"], reverse=True)
    by_units = sorted(enriched, key=lambda x: x["units_sold"], reverse=True)

    top_rev = by_revenue[0]
    top_unit = by_units[0]

    # Handle ties
    top_rev_winners = [r for r in by_revenue if r["net_revenue"] == top_rev["net_revenue"]]
    top_unit_winners = [r for r in by_units if r["units_sold"] == top_unit["units_sold"]]

    if top_rev["region"] == top_unit["region"]:
        narrative = (
            f"The region generating the highest sales is {top_rev['region']}, leading in both "
            f"revenue (₹{top_rev['net_revenue']:,.2f}, {top_rev['revenue_share_percent']}% share) "
            f"and volume ({top_rev['units_sold']:,} units, {top_rev['units_share_percent']}% share)."
        )
    else:
        narrative = (
            f"By net revenue, the top region is {top_rev['region']} (₹{top_rev['net_revenue']:,.2f}); "
            f"by volume sold, the top region is {top_unit['region']} ({top_unit['units_sold']:,} units)."
        )

    return {
        "metric": "top_region",
        "top_region_by_revenue": top_rev["region"] if len(top_rev_winners) == 1 else [r["region"] for r in top_rev_winners],
        "top_revenue_value": top_rev["net_revenue"],
        "top_region_by_units": top_unit["region"] if len(top_unit_winners) == 1 else [r["region"] for r in top_unit_winners],
        "top_units_value": top_unit["units_sold"],
        "is_unanimous_leader": top_rev["region"] == top_unit["region"],
        "ranking_by_revenue": by_revenue,
        "ranking_by_units": by_units,
        "narrative": narrative,
    }

def get_revenue_delta(
    month_a: str, 
    month_b: str, 
    db_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Compare revenue between two months chronologically, calculating absolute and percentage changes.
    
    Accepts arbitrary order (e.g. ('April', 'May') or ('2026-05', '2026-04')).
    Automatically arranges baseline (earlier) and target (later) chronologically.
    """
    iso_a = normalize_month(month_a)
    iso_b = normalize_month(month_b)

    # Chronological sort: earlier is baseline, later is comparison target
    if iso_a > iso_b:
        base_month, target_month = iso_b, iso_a
    else:
        base_month, target_month = iso_a, iso_b

    query_sql = """
    SELECT 
        strftime('%Y-%m', order_date) AS month,
        COALESCE(ROUND(SUM(net_amount), 2), 0.0) AS net_revenue,
        COALESCE(ROUND(SUM(gross_amount), 2), 0.0) AS gross_revenue,
        COALESCE(SUM(quantity), 0) AS units_sold,
        COUNT(*) AS transaction_count
    FROM sales_transactions
    WHERE is_valid_for_revenue = 1 AND order_date IS NOT NULL
      AND strftime('%Y-%m', order_date) IN (?, ?)
    GROUP BY month;
    """
    rows = execute_read_query(query_sql, (base_month, target_month), db_path=db_path)
    lookup = {r["month"]: r for r in rows}

    base_data = lookup.get(base_month, {
        "month": base_month, "net_revenue": 0.0, "gross_revenue": 0.0, "units_sold": 0, "transaction_count": 0
    })
    target_data = lookup.get(target_month, {
        "month": target_month, "net_revenue": 0.0, "gross_revenue": 0.0, "units_sold": 0, "transaction_count": 0
    })

    base_rev = base_data["net_revenue"]
    target_rev = target_data["net_revenue"]
    absolute_change = round(target_rev - base_rev, 2)

    if base_rev > 0:
        pct_change = round((absolute_change / base_rev) * 100, 2)
    elif target_rev > 0:
        pct_change = 100.0  # From zero to positive
    else:
        pct_change = 0.0

    if absolute_change > 0:
        direction = "increased"
        sign = "+"
    elif absolute_change < 0:
        direction = "decreased"
        sign = ""
    else:
        direction = "remained unchanged"
        sign = ""

    narrative = (
        f"Revenue {direction} from {base_month} (₹{base_rev:,.2f}) to {target_month} (₹{target_rev:,.2f}) "
        f"by {sign}₹{abs(absolute_change):,.2f} ({sign}{pct_change}%)."
    )

    return {
        "metric": "revenue_delta",
        "base_month": base_month,
        "base_revenue": base_rev,
        "base_data": base_data,
        "target_month": target_month,
        "target_revenue": target_rev,
        "target_data": target_data,
        "absolute_change": absolute_change,
        "percentage_change": pct_change,
        "direction": direction,
        "narrative": narrative,
    }

# Allowlisted Analytics Registry for Secure Dispatch
ALLOWED_ANALYTICS_REGISTRY = {
    "get_total_revenue": get_total_revenue,
    "get_top_product": get_top_product,
    "get_monthly_revenue_trend": get_monthly_revenue_trend,
    "get_top_region": get_top_region,
    "get_revenue_delta": get_revenue_delta,
}

def run_analytics(func_name: str, **kwargs: Any) -> Dict[str, Any]:
    """Execute an allowlisted analytics function with strict dispatch validation."""
    if func_name not in ALLOWED_ANALYTICS_REGISTRY:
        raise ValueError(
            f"Unauthorized or unknown analytics function: '{func_name}'. "
            f"Allowed functions: {sorted(list(ALLOWED_ANALYTICS_REGISTRY.keys()))}"
        )
    return ALLOWED_ANALYTICS_REGISTRY[func_name](**kwargs)
