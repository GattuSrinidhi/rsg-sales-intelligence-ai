# Deterministic Analytics Specification

## 1. Overview
The **Deterministic Analytics Engine** ([`src/analytics.py`](../src/analytics.py)) provides mathematically verified, tamper-proof calculations for all business intelligence questions defined in the official challenge.

Rather than relying on non-deterministic LLM calculations, the system uses strict SQL aggregation and verified Python logic. This Vectorless RAG approach guarantees that answers are always 100% reproducible and grounded in verified database facts.

---

## 2. Core Business Formulas & Data Eligibility Rules

### Financial Calculation Formulas
1. **Gross Transaction Value**:
   $$\text{Gross Revenue} = \text{Quantity} \times \text{Unit Price}$$
2. **Net Revenue (Primary Metric)**:
   $$\text{Net Revenue} = \text{Gross Revenue} - \text{Discount Amount}$$
3. **Month-over-Month (MoM) Absolute Delta**:
   $$\Delta_{\text{abs}} = \text{Revenue}_{\text{target}} - \text{Revenue}_{\text{baseline}}$$
4. **Month-over-Month (MoM) Percentage Delta**:
   $$\Delta_{\%} = \left( \frac{\text{Revenue}_{\text{target}} - \text{Revenue}_{\text{baseline}}}{\text{Revenue}_{\text{baseline}}} \right) \times 100$$

### Data Eligibility & Filtering Rules
* Only transactions marked with `is_valid_for_revenue = 1` are aggregated into revenue metrics.
* **Returned Transactions** (`Status = 'Returned'`, e.g., `TXN0033`): Excluded from earned revenue (`is_valid_for_revenue = 0`).
* **Missing Prices** (`Unit_price IS NULL`, e.g., `TXN0051`): Excluded from revenue aggregation (`is_valid_for_revenue = 0`).
* **Zero Quantity** (`Quantity = 0`, e.g., `TXN0034`): Preserved as valid audit record, contributing ₹0.00.
* **Date Integrity**: Chronological queries strictly enforce `order_date IS NOT NULL` (invalid dates are set to NULL during ingestion).

---

## 3. Official Business Questions & Functional Coverage

### Question 1: Total Revenue
* **Function**: `get_total_revenue(db_path=None)`
* **SQL Query**:
  ```sql
  SELECT 
      ROUND(SUM(net_amount), 2) AS total_net_revenue,
      ROUND(SUM(gross_amount), 2) AS total_gross_revenue,
      ROUND(SUM(discount_amount), 2) AS total_discount_amount,
      SUM(quantity) AS total_units_sold,
      COUNT(*) AS valid_transaction_count
  FROM sales_transactions
  WHERE is_valid_for_revenue = 1;
  ```
* **Ground Truth Result**:
  * **Total Net Revenue**: **₹1,439,200.00**
  * **Total Gross Revenue**: ₹1,443,700.00
  * **Total Discounts**: ₹4,500.00
  * **Total Units Sold**: 633 units
  * **Valid Transactions**: 49 transactions

### Question 2: Product with the Highest Revenue
* **Function**: `get_top_product(metric="revenue", db_path=None)`
* **Ground Truth Result**:
  * **Top Product by Net Revenue**: **`Monitor`** with **₹473,000.00** (Gross: ₹475,000.00; 50 units sold across 9 transactions).
  * **Runner-Up #2**: `Desk` with ₹222,500.00.
  * **Volume Insight**: By *units sold*, the top product is **`Wireless Mouse`** with **228 units** (₹148,200.00).
* **Tie Handling**: If multiple products tie for the top position, `is_tie = True` and all tying products are returned in `winners`.

### Question 3: Monthly Revenue Trend
* **Function**: `get_monthly_revenue_trend(db_path=None)`
* **Ground Truth Result (H1 2026)**:
  * **2026-01**: ₹210,250.00 (8 transactions, 80 units)
  * **2026-02**: ₹234,600.00 (8 transactions, 116 units) — *+₹24,350.00 (+11.58% MoM)*
  * **2026-03**: ₹223,900.00 (8 transactions, 93 units) — *-₹10,700.00 (-4.56% MoM)*
  * **2026-04**: ₹240,700.00 (9 transactions, 127 units) — *+₹16,800.00 (+7.50% MoM)*
  * **2026-05**: ₹318,500.00 (8 transactions, 116 units) — *+₹77,800.00 (+32.32% MoM) [PEAK MONTH]*
  * **2026-06**: ₹211,250.00 (8 transactions, 101 units) — *-₹107,250.00 (-33.67% MoM)*
  * **Average Monthly Revenue**: ₹239,866.67/month.

### Question 4: Region with the Highest Sales
* **Function**: `get_top_region(metric="revenue", db_path=None)`
* **Resolution of "Highest Sales" Ambiguity**:
  * In sales analytics, "Sales" can mean monetary revenue (₹) or physical volume (units).
  * The engine calculates and returns both dimensions explicitly.
* **Ground Truth Result**:
  * **Top Region by Net Revenue**: **`South`** with **₹411,200.00** (28.57% revenue share).
  * **Top Region by Units Sold**: **`South`** with **182 units** (28.75% unit share).
  * **Unanimous Leader**: `is_unanimous_leader = True` because `South` leads under both definitions.
  * **Complete Regional Ranking**:
    1. South: ₹411,200.00 (182 units)
    2. North: ₹384,450.00 (148 units)
    3. East: ₹346,700.00 (126 units)
    4. West: ₹296,850.00 (139 units)

### Question 5: Revenue Change Between Two Specified Months
* **Function**: `get_revenue_delta(month_a, month_b, db_path=None)`
* **Features**:
  * Flexible month parsing (accepts `"April"`, `"04"`, `"2026-04"`, `"April 2026"`, etc.).
  * Automatic chronological ordering: always treats the earlier month as the baseline and the later month as the comparison target.
  * Reports absolute delta (₹), percentage delta (%), and qualitative direction (`"increased"`, `"decreased"`, `"remained unchanged"`).
* **Example Ground Truth (April to May)**:
  * Baseline (2026-04): ₹240,700.00
  * Target (2026-05): ₹318,500.00
  * Absolute Change: **+₹77,800.00**
  * Percentage Change: **+32.32%**
  * Direction: `"increased"`

---

## 4. Security & Allowlisting Architecture
* Direct user input is **never** concatenated into raw SQL strings.
* Only allowlisted analytics functions registered in `ALLOWED_ANALYTICS_REGISTRY` can be dispatched via `run_analytics(func_name, **kwargs)`.
* Read-only connection guarantees that no analytics call can modify, delete, or drop database state.
