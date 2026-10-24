"""Unit and regression tests for the deterministic sales analytics engine."""

import pytest
import sqlite3
from src.analytics import (
    get_total_revenue,
    get_top_product,
    get_monthly_revenue_trend,
    get_top_region,
    get_revenue_delta,
    normalize_month,
    run_analytics,
    ALLOWED_ANALYTICS_REGISTRY,
)
from src.db import init_db

# 1. Total Revenue Tests
def test_get_total_revenue(populated_db):
    """Verify total revenue matches verified mathematical ground truth."""
    res = get_total_revenue(db_path=populated_db)
    assert res["metric"] == "total_revenue"
    assert res["total_net_revenue"] == 1439200.0
    assert res["total_gross_revenue"] == 1443700.0
    assert res["total_discount_amount"] == 4500.0
    assert res["total_units_sold"] == 633
    assert res["valid_transaction_count"] == 49
    assert len(res["category_breakdown"]) == 3
    assert len(res["channel_breakdown"]) == 2
    assert "₹1,439,200.00" in res["narrative"]

# 2. Top Product Tests
def test_get_top_product_by_revenue(populated_db):
    """Verify top product by revenue is Monitor with ₹473,000.00."""
    res = get_top_product(metric="revenue", db_path=populated_db)
    assert res["metric"] == "top_product"
    assert res["top_product"] == "Monitor"
    assert res["top_value"] == 473000.0
    assert res["is_tie"] is False
    assert len(res["ranking"]) == 7
    # Runner up is Desk
    assert res["ranking"][1]["product"] == "Desk"
    assert res["ranking"][1]["net_revenue"] == 222500.0

def test_get_top_product_by_units(populated_db):
    """Verify top product by volume sold is Wireless Mouse with 228 units."""
    res = get_top_product(metric="units", db_path=populated_db)
    assert res["metric"] == "top_product"
    assert res["top_product"] == "Wireless Mouse"
    assert res["top_value"] == 228
    assert res["ranking"][0]["units_sold"] == 228

# 3. Monthly Revenue Trend Tests
def test_get_monthly_revenue_trend(populated_db):
    """Verify monthly revenue figures and MoM delta calculations."""
    res = get_monthly_revenue_trend(db_path=populated_db)
    trend = res["trend"]
    assert len(trend) == 6

    # Verify each month's net revenue
    expected = {
        "2026-01": 210250.0,
        "2026-02": 234600.0,
        "2026-03": 223900.0,
        "2026-04": 240700.0,
        "2026-05": 318500.0,
        "2026-06": 211250.0,
    }
    for m in trend:
        assert m["net_revenue"] == expected[m["month"]]

    # Jan has no prior month
    assert trend[0]["mom_change_amount"] is None
    assert trend[0]["mom_change_percent"] is None

    # Feb MoM: 234600 - 210250 = +24350 (+11.58%)
    assert trend[1]["mom_change_amount"] == 24350.0
    assert trend[1]["mom_change_percent"] == 11.58

    # May is peak month
    assert res["peak_month"]["month"] == "2026-05"
    assert res["peak_month"]["net_revenue"] == 318500.0

    # Jan is lowest month
    assert res["lowest_month"]["month"] == "2026-01"
    assert res["lowest_month"]["net_revenue"] == 210250.0

    # Average
    assert res["average_monthly_revenue"] == 239866.67

# 4. Top Region Tests (Revenue vs Units)
def test_get_top_region_sales(populated_db):
    """Verify top region for both revenue and units is South."""
    res = get_top_region(db_path=populated_db)
    assert res["top_region_by_revenue"] == "South"
    assert res["top_revenue_value"] == 411200.0
    assert res["top_region_by_units"] == "South"
    assert res["top_units_value"] == 182
    assert res["is_unanimous_leader"] is True

    # Complete regional revenue ranking
    rev_ranking = res["ranking_by_revenue"]
    assert [r["region"] for r in rev_ranking] == ["South", "North", "East", "West"]
    assert rev_ranking[0]["net_revenue"] == 411200.0
    assert rev_ranking[1]["net_revenue"] == 384450.0
    assert rev_ranking[2]["net_revenue"] == 346700.0
    assert rev_ranking[3]["net_revenue"] == 296850.0

# 5. Revenue Delta Tests
def test_get_revenue_delta_increase(populated_db):
    """Verify April to May revenue increase calculation."""
    res = get_revenue_delta("April", "May", db_path=populated_db)
    assert res["base_month"] == "2026-04"
    assert res["base_revenue"] == 240700.0
    assert res["target_month"] == "2026-05"
    assert res["target_revenue"] == 318500.0
    assert res["absolute_change"] == 77800.0
    assert res["percentage_change"] == 32.32
    assert res["direction"] == "increased"

def test_get_revenue_delta_decrease(populated_db):
    """Verify May to June revenue decrease calculation."""
    res = get_revenue_delta("2026-05", "2026-06", db_path=populated_db)
    assert res["base_month"] == "2026-05"
    assert res["base_revenue"] == 318500.0
    assert res["target_month"] == "2026-06"
    assert res["target_revenue"] == 211250.0
    assert res["absolute_change"] == -107250.0
    assert res["percentage_change"] == -33.67
    assert res["direction"] == "decreased"

def test_get_revenue_delta_reversed_input_order(populated_db):
    """Verify that passing months in reverse order still sorts chronologically."""
    res = get_revenue_delta("June", "January", db_path=populated_db)
    assert res["base_month"] == "2026-01"
    assert res["target_month"] == "2026-06"
    assert res["absolute_change"] == 1000.0
    assert res["percentage_change"] == 0.48
    assert res["direction"] == "increased"

# 6. Normalization & Input Validation Tests
def test_normalize_month():
    """Verify flexible month string parsing and error rejection."""
    assert normalize_month("April") == "2026-04"
    assert normalize_month("apr") == "2026-04"
    assert normalize_month("04") == "2026-04"
    assert normalize_month("4") == "2026-04"
    assert normalize_month("2026-04") == "2026-04"
    assert normalize_month("2026/05") == "2026-05"
    assert normalize_month("May 2026") == "2026-05"

    with pytest.raises(ValueError, match="Unrecognized month format"):
        normalize_month("NotAMonth")

    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_month("")

# 7. Edge Cases: Empty Database Handling
def test_analytics_empty_database(temp_db_path):
    """Verify all analytics functions handle an empty database gracefully without crashing."""
    r_total = get_total_revenue(db_path=temp_db_path)
    assert r_total["total_net_revenue"] == 0.0
    assert r_total["valid_transaction_count"] == 0

    r_prod = get_top_product(db_path=temp_db_path)
    assert r_prod["top_value"] == 0.0
    assert r_prod["all_products"] == []

    r_trend = get_monthly_revenue_trend(db_path=temp_db_path)
    assert r_trend["trend"] == []
    assert r_trend["total_months"] == 0

    r_reg = get_top_region(db_path=temp_db_path)
    assert r_reg["top_region_revenue"] is None

    r_delta = get_revenue_delta("April", "May", db_path=temp_db_path)
    assert r_delta["base_revenue"] == 0.0
    assert r_delta["target_revenue"] == 0.0
    assert r_delta["absolute_change"] == 0.0
    assert r_delta["percentage_change"] == 0.0

# 8. Edge Cases: Ties Handling
def test_top_product_ties_handling(temp_db_path):
    """Verify that multiple products sharing the same highest revenue are reported as a tie."""
    conn = sqlite3.connect(temp_db_path)
    conn.execute("""
        INSERT INTO sales_transactions (
            transaction_id, order_date_raw, order_date, product, category,
            region, sales_channel, quantity, unit_price, discount_amount,
            gross_amount, net_amount, status, data_flag, is_valid_for_revenue
        ) VALUES 
        ('T1', '01-01-2026', '2026-01-01', 'ItemA', 'Cat', 'North', 'Online', 1, 5000, 0, 5000, 5000, 'Completed', 'VALID', 1),
        ('T2', '01-01-2026', '2026-01-01', 'ItemB', 'Cat', 'South', 'Retail', 1, 5000, 0, 5000, 5000, 'Completed', 'VALID', 1);
    """)
    conn.commit()
    conn.close()

    res = get_top_product(metric="revenue", db_path=temp_db_path)
    assert res["is_tie"] is True
    assert set(res["top_product"]) == {"ItemA", "ItemB"}
    assert res["top_value"] == 5000.0

# 9. Allowlisted Dispatcher Security Test
def test_run_analytics_dispatcher(populated_db):
    """Verify that the dispatcher executes allowed functions and rejects unauthorized calls."""
    res = run_analytics("get_total_revenue", db_path=populated_db)
    assert res["total_net_revenue"] == 1439200.0

    with pytest.raises(ValueError, match="Unauthorized or unknown analytics function"):
        run_analytics("malicious_or_unknown_function")
