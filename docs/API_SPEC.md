# FastAPI Backend API Specification

## 1. Overview
The **RSG Sales Intelligence Backend API** ([`src/main.py`](../src/main.py)) is a high-performance REST service built on **FastAPI**. It securely exposes the Vectorless RAG AI Agent and the Deterministic Analytics Engine.

### Base URL
`http://127.0.0.1:8000`

### Interactive OpenAPI Documentation
* **Swagger UI**: `http://127.0.0.1:8000/docs`
* **ReDoc**: `http://127.0.0.1:8000/redoc`

---

## 2. API Endpoints

### 1. Health Check
* **Route**: `GET /api/health`
* **Summary**: Returns server health, SQLite connection state, total records, and Gemini configuration status.
* **Response Status**: `200 OK`
* **Example Response**:
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "database_connected": true,
  "gemini_configured": false,
  "total_records": 51,
  "valid_revenue_records": 49,
  "timestamp": "2026-10-24T17:39:10.123456Z"
}
```

---

### 2. Natural Language Query
* **Route**: `POST /api/query`
* **Summary**: Accepts natural language sales questions, executes Vectorless RAG via Gemini / Deterministic Fallback, and returns grounded answers.
* **Request Body**:
```json
{
  "question": "What is the total revenue?"
}
```
* **Validation Rules**:
  * `question`: string (minimum length: 1, maximum length: 500). Blank or whitespace-only strings return `400 Bad Request`.
* **Response Status**: `200 OK`
* **Example Response**:
```json
{
  "success": true,
  "query": "What is the total revenue?",
  "intent": "TOTAL_REVENUE",
  "engine": "deterministic_fallback",
  "answer": "The total net revenue generated is ₹1,439,200.00 across 49 valid completed transactions (Gross: ₹1,443,700.00, Total Discounts: ₹4,500.00, Total Units: 633).",
  "supporting_data": {
    "metric": "total_revenue",
    "total_net_revenue": 1439200.0,
    "total_gross_revenue": 1443700.0,
    "total_discount_amount": 4500.0,
    "total_units_sold": 633,
    "valid_transaction_count": 49,
    "category_breakdown": [
      {"category": "Accessories", "net_revenue": 533100.0, "units_sold": 451, "transaction_count": 28},
      {"category": "Electronics", "net_revenue": 473000.0, "units_sold": 50, "transaction_count": 9},
      {"category": "Furniture", "net_revenue": 433100.0, "units_sold": 132, "transaction_count": 12}
    ]
  },
  "execution_trace": {
    "intent": "TOTAL_REVENUE",
    "metric": "revenue",
    "tool_called": "get_total_revenue",
    "parameters": {"month_a": null, "month_b": null},
    "latency_ms": 4.12,
    "is_safe": true
  }
}
```

---

### 3. Direct Deterministic Analytics Endpoints

| Method | Endpoint | Query Parameters | Description |
|---|---|---|---|
| `GET` | `/api/analytics/total-revenue` | None | Direct calculation of Net Revenue, Gross Revenue, and Discounts. |
| `GET` | `/api/analytics/top-product` | `metric: 'revenue' \| 'units'` | Direct calculation of top product by net revenue or volume. |
| `GET` | `/api/analytics/monthly-trend` | None | Direct retrieval of chronological monthly revenue series with MoM deltas. |
| `GET` | `/api/analytics/top-region` | `metric: 'revenue' \| 'units'` | Direct regional sales analysis with revenue and unit shares. |
| `GET` | `/api/analytics/revenue-delta` | `month_a`, `month_b` | Direct calculation of revenue delta between two months. |

---

## 3. Error Handling & Security Model

All errors return a standardized JSON structure with appropriate HTTP status codes:

```json
{
  "error": "Question cannot be blank or contain only whitespace.",
  "error_type": "HTTPException",
  "status_code": 400
}
```

### HTTP Status Codes:
* **`200 OK`**: Successful query processing, including graceful clarification or out-of-scope guidance.
* **`400 Bad Request`**: Blank/whitespace questions or invalid query parameters (e.g. unrecognized month name).
* **`422 Unprocessable Entity`**: Request schema validation failure (e.g. missing `question` key or string > 500 characters).
* **`500 Internal Server Error`**: Safe generic error response. **Stack traces, internal file paths, and database details are never leaked.**

---

## 4. Local Execution Instructions

To start the API server locally on Windows:

```powershell
# From project root
.\.venv\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```
