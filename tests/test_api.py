"""Unit and integration tests for the FastAPI backend API."""

import json
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app)

# --- 1. Health Endpoint Tests ---

def test_health_check_endpoint():
    """Verify health endpoint reports healthy database status and record counts."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert data["version"] == "1.0.0"
    assert data["database_connected"] is True
    assert data["total_records"] == 51
    assert data["valid_revenue_records"] == 49
    assert "timestamp" in data

# --- 2. Query Endpoint Tests for All 5 Official Business Intents ---

def test_query_total_revenue_official():
    """Verify POST /api/query answers total revenue accurately."""
    response = client.post("/api/query", json={"question": "What is the total revenue?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "TOTAL_REVENUE"
    assert "₹1,439,200.00" in data["answer"]
    assert data["supporting_data"]["total_net_revenue"] == 1439200.0
    assert data["execution_trace"]["tool_called"] == "get_total_revenue"

def test_query_top_product_official():
    """Verify POST /api/query answers top product accurately."""
    response = client.post("/api/query", json={"question": "Which product generated the highest revenue?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "TOP_PRODUCT"
    assert "Monitor" in data["answer"]
    assert data["supporting_data"]["top_product"] == "Monitor"

def test_query_monthly_trend_official():
    """Verify POST /api/query answers monthly revenue trend accurately."""
    response = client.post("/api/query", json={"question": "What is the monthly revenue trend?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "MONTHLY_TREND"
    assert len(data["supporting_data"]["trend"]) == 6
    assert data["supporting_data"]["peak_month"]["month"] == "2026-05"

def test_query_top_region_official():
    """Verify POST /api/query answers top region accurately."""
    response = client.post("/api/query", json={"question": "Which region generated the highest sales?"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "TOP_REGION"
    assert "South" in data["answer"]
    assert data["supporting_data"]["top_region_by_revenue"] == "South"

def test_query_revenue_delta_official():
    """Verify POST /api/query answers month-to-month change accurately."""
    response = client.post(
        "/api/query",
        json={"question": "How did revenue change between April and May?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["intent"] == "REVENUE_DELTA"
    assert "+₹77,800.00" in data["answer"]
    assert "+32.32%" in data["answer"]
    assert data["supporting_data"]["absolute_change"] == 77800.0

# --- 3. Input Validation and Boundary Tests ---

def test_query_empty_string():
    """Verify that an empty string question is rejected with 422."""
    response = client.post("/api/query", json={"question": ""})
    assert response.status_code == 422
    data = response.json()
    assert data["error_type"] == "RequestValidationError"

def test_query_whitespace_only():
    """Verify that whitespace-only questions are rejected with 400 Bad Request."""
    response = client.post("/api/query", json={"question": "    "})
    assert response.status_code == 400
    data = response.json()
    assert "cannot be blank" in data["error"]

def test_query_oversized_string():
    """Verify that questions exceeding 500 characters are rejected with 422."""
    oversized = "What is the total revenue? " + ("A" * 500)
    response = client.post("/api/query", json={"question": oversized})
    assert response.status_code == 422
    data = response.json()
    assert data["error_type"] == "RequestValidationError"

def test_query_invalid_payload_schema():
    """Verify that malformed JSON payloads missing 'question' are rejected with 422."""
    response = client.post("/api/query", json={"invalid_field": "some text"})
    assert response.status_code == 422
    data = response.json()
    assert data["error_type"] == "RequestValidationError"

# --- 4. Unsupported Questions and Clarification Handling ---

def test_query_missing_parameters_clarification():
    """Verify that incomplete queries return 200 OK with clarification prompt, not server error."""
    response = client.post(
        "/api/query",
        json={"question": "How did revenue change between two months?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "CLARIFICATION_NEEDED"
    assert "specify both months" in data["answer"]

def test_query_out_of_scope_question():
    """Verify that out-of-scope questions return 200 OK with guidance, not 500 error."""
    response = client.post(
        "/api/query",
        json={"question": "What is the capital of France?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "UNKNOWN"
    assert "I specialize in sales intelligence" in data["answer"]

# --- 5. Gemini Engine Verification via Mocking ---

@patch("src.agent.classify_intent_with_gemini")
def test_query_gemini_engine_success(mock_gemini):
    """Verify that API reports engine='gemini' when Gemini succeeds."""
    from src.agent import QueryIntent, IntentType, MetricType

    mock_gemini.return_value = QueryIntent(
        intent=IntentType.TOTAL_REVENUE,
        metric=MetricType.REVENUE,
        confidence=0.98
    )

    response = client.post(
        "/api/query",
        json={"question": "What is the total revenue?"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["engine"] == "gemini"
    assert data["intent"] == "TOTAL_REVENUE"
    assert "₹1,439,200.00" in data["answer"]

# --- 6. Direct Deterministic Analytics Endpoints ---

def test_direct_analytics_total_revenue():
    response = client.get("/api/analytics/total-revenue")
    assert response.status_code == 200
    data = response.json()
    assert data["total_net_revenue"] == 1439200.0

def test_direct_analytics_top_product():
    response = client.get("/api/analytics/top-product?metric=revenue")
    assert response.status_code == 200
    data = response.json()
    assert data["top_product"] == "Monitor"

def test_direct_analytics_top_product_invalid_metric():
    response = client.get("/api/analytics/top-product?metric=invalid_metric")
    assert response.status_code == 400
    assert "must be either 'revenue' or 'units'" in response.json()["error"]

def test_direct_analytics_monthly_trend():
    response = client.get("/api/analytics/monthly-trend")
    assert response.status_code == 200
    data = response.json()
    assert len(data["trend"]) == 6

def test_direct_analytics_top_region():
    response = client.get("/api/analytics/top-region")
    assert response.status_code == 200
    data = response.json()
    assert data["top_region_by_revenue"] == "South"

def test_direct_analytics_revenue_delta():
    response = client.get("/api/analytics/revenue-delta?month_a=April&month_b=May")
    assert response.status_code == 200
    data = response.json()
    assert data["absolute_change"] == 77800.0

def test_direct_analytics_revenue_delta_invalid_month():
    response = client.get("/api/analytics/revenue-delta?month_a=InvalidMonth&month_b=May")
    assert response.status_code == 400
    assert "Unrecognized month format" in response.json()["error"]

# --- 7. Security and Safe Error Handling ---

@patch("src.main.process_query")
def test_unhandled_internal_error_safety(mock_process):
    """Verify that unexpected internal errors return safe 500 without leaking stack traces or paths."""
    mock_process.side_effect = RuntimeError("Simulated internal database connection drop")

    client_safe = TestClient(app, raise_server_exceptions=False)
    response = client_safe.post("/api/query", json={"question": "What is the total revenue?"})
    assert response.status_code == 500
    data = response.json()
    assert data["error_type"] == "InternalServerError"
    assert "internal server error occurred" in data["error"]
    # Ensure sensitive details are not leaked
    assert "Simulated internal database" not in data["error"]
    assert "Traceback" not in data["error"]
    assert "C:\\" not in data["error"]

# --- 8. Frontend Static Files Serving Tests ---

def test_frontend_index_served():
    """Verify that root / returns the frontend dashboard HTML."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers.get("content-type", "")
    assert "RSG Sales Intelligence AI Assistant" in response.text
    assert "queryForm" in response.text

def test_frontend_styles_served():
    """Verify that /styles.css is served successfully."""
    response = client.get("/styles.css")
    assert response.status_code == 200
    assert "text/css" in response.headers.get("content-type", "")
    assert "--bg-primary" in response.text

def test_frontend_script_served():
    """Verify that /app.js is served successfully."""
    response = client.get("/app.js")
    assert response.status_code == 200
    assert "javascript" in response.headers.get("content-type", "")
    assert "checkSystemHealth" in response.text
