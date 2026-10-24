"""Unit and integration tests for the AI Agent and Vectorless RAG engine."""

import json
from unittest.mock import MagicMock, patch
import pytest

from src.agent import (
    IntentType,
    MetricType,
    QueryIntent,
    AgentResponse,
    classify_intent_deterministic,
    classify_intent_with_gemini,
    process_query,
)

# --- 1. Deterministic Classifier Tests (All 5 Official Questions) ---

def test_deterministic_total_revenue_official():
    intent = classify_intent_deterministic("What is the total revenue?")
    assert intent.intent == IntentType.TOTAL_REVENUE
    assert intent.metric == MetricType.REVENUE

def test_deterministic_top_product_official():
    intent = classify_intent_deterministic("Which product generated the highest revenue?")
    assert intent.intent == IntentType.TOP_PRODUCT
    assert intent.metric == MetricType.REVENUE

def test_deterministic_monthly_trend_official():
    intent = classify_intent_deterministic("What is the monthly revenue trend?")
    assert intent.intent == IntentType.MONTHLY_TREND

def test_deterministic_top_region_official():
    intent = classify_intent_deterministic("Which region generated the highest sales?")
    assert intent.intent == IntentType.TOP_REGION

def test_deterministic_revenue_delta_official():
    intent = classify_intent_deterministic("How did revenue change between April and May?")
    assert intent.intent == IntentType.REVENUE_DELTA
    assert intent.month_a.lower() == "april"
    assert intent.month_b.lower() == "may"

# --- 2. Natural Language Paraphrases & Variations ---

@pytest.mark.parametrize("query,expected_intent", [
    ("How much money did the company make in total?", IntentType.TOTAL_REVENUE),
    ("Give me the overall sales revenue", IntentType.TOTAL_REVENUE),
    ("What was our top selling product by revenue?", IntentType.TOP_PRODUCT),
    ("Which item generated the most revenue?", IntentType.TOP_PRODUCT),
    ("Show me the sales trend month by month", IntentType.MONTHLY_TREND),
    ("How did revenue evolve over time?", IntentType.MONTHLY_TREND),
    ("Which territory had the best sales?", IntentType.TOP_REGION),
    ("What is the regional sales breakdown?", IntentType.TOP_REGION),
    ("Compare revenue between 2026-02 and 2026-05", IntentType.REVENUE_DELTA),
    ("What was the difference between Jan and March?", IntentType.REVENUE_DELTA),
])
def test_paraphrase_classification(query, expected_intent):
    intent = classify_intent_deterministic(query)
    assert intent.intent == expected_intent

def test_metric_detection_units():
    """Verify that questions specifying units or volume switch metric to 'units'."""
    intent_prod = classify_intent_deterministic("Which product had the highest volume of units sold?")
    assert intent_prod.intent == IntentType.TOP_PRODUCT
    assert intent_prod.metric == MetricType.UNITS

    intent_reg = classify_intent_deterministic("Which region sold the most units?")
    assert intent_reg.intent == IntentType.TOP_REGION
    assert intent_reg.metric == MetricType.UNITS

# --- 3. Parameter Extraction & Missing Parameter Handling ---

def test_revenue_delta_missing_months():
    """Verify that asking for revenue change without specifying months asks for clarification."""
    intent = classify_intent_deterministic("How did revenue change between two months?")
    assert intent.intent == IntentType.CLARIFICATION_NEEDED
    assert "specify both months" in intent.clarification_message

def test_revenue_delta_only_one_month():
    intent = classify_intent_deterministic("How did revenue change compared to April?")
    assert intent.intent == IntentType.CLARIFICATION_NEEDED
    assert "specify both months" in intent.clarification_message

def test_unknown_and_out_of_scope_query():
    """Verify that non-sales questions are classified as UNKNOWN."""
    intent = classify_intent_deterministic("What is the weather in Mumbai?")
    assert intent.intent == IntentType.UNKNOWN
    assert "I could not recognize your question" in intent.clarification_message

# --- 4. End-to-End process_query with Deterministic Fallback ---

def test_process_query_total_revenue_grounded(populated_db):
    """Verify process_query returns verified ground truth revenue without AI hallucination."""
    res = process_query("What is the total revenue?", db_path=populated_db)
    assert res.success is True
    assert res.engine == "deterministic_fallback"
    assert res.intent == "TOTAL_REVENUE"
    assert "₹1,439,200.00" in res.answer
    assert res.supporting_data["total_net_revenue"] == 1439200.0
    assert res.execution_trace["tool_called"] == "get_total_revenue"
    assert res.execution_trace["is_safe"] is True

def test_process_query_top_product_grounded(populated_db):
    """Verify process_query correctly identifies Monitor as highest revenue earner."""
    res = process_query("Which product generated the highest revenue?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "TOP_PRODUCT"
    assert "Monitor" in res.answer
    assert "₹473,000.00" in res.answer
    assert res.supporting_data["top_product"] == "Monitor"

def test_process_query_monthly_trend_grounded(populated_db):
    """Verify process_query returns monthly trend data grounded in SQLite."""
    res = process_query("What is the monthly revenue trend?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "MONTHLY_TREND"
    assert len(res.supporting_data["trend"]) == 6
    assert res.supporting_data["peak_month"]["month"] == "2026-05"

def test_process_query_top_region_grounded(populated_db):
    """Verify process_query correctly identifies South as top region."""
    res = process_query("Which region generated the highest sales?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "TOP_REGION"
    assert "South" in res.answer
    assert res.supporting_data["top_region_by_revenue"] == "South"

def test_process_query_revenue_delta_grounded(populated_db):
    """Verify process_query computes April to May delta accurately."""
    res = process_query("How did revenue change between April and May?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "REVENUE_DELTA"
    assert "+₹77,800.00" in res.answer
    assert "+32.32%" in res.answer
    assert res.supporting_data["absolute_change"] == 77800.0

def test_process_query_missing_parameters_clarification(populated_db):
    """Verify that missing parameters return a helpful clarification instead of crashing."""
    res = process_query("How did revenue change between two months?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "CLARIFICATION_NEEDED"
    assert "specify both months" in res.answer

def test_process_query_unknown_question(populated_db):
    """Verify that unknown questions guide the user politely."""
    res = process_query("Who won the 2026 World Cup?", db_path=populated_db)
    assert res.success is True
    assert res.intent == "UNKNOWN"
    assert "I specialize in sales intelligence" in res.answer

# --- 5. Mocked Gemini Runtime Integration Tests ---

@patch("google.genai.Client")
def test_classify_intent_with_gemini_success(mock_client_class):
    """Verify Gemini SDK invocation and strict Pydantic parsing when model succeeds."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "intent": "TOTAL_REVENUE",
        "metric": "revenue",
        "confidence": 0.99
    })
    mock_client.models.generate_content.return_value = mock_response

    intent = classify_intent_with_gemini("Tell me our company's earnings", api_key="AIzaSyMockKey")
    assert intent.intent == IntentType.TOTAL_REVENUE
    assert intent.confidence == 0.99
    mock_client.models.generate_content.assert_called_once()

@patch("google.genai.Client")
def test_process_query_with_gemini_engine(mock_client_class, populated_db):
    """Verify process_query uses 'gemini' engine when Gemini succeeds."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = json.dumps({
        "intent": "TOP_PRODUCT",
        "metric": "revenue",
        "confidence": 0.95
    })
    mock_client.models.generate_content.return_value = mock_response

    res = process_query(
        "What is our most lucrative product?",
        db_path=populated_db,
        api_key="AIzaSyMockKey"
    )
    assert res.engine == "gemini"
    assert res.intent == "TOP_PRODUCT"
    assert "Monitor" in res.answer
    assert res.supporting_data["top_product"] == "Monitor"

@patch("google.genai.Client")
def test_gemini_malformed_response_fallback(mock_client_class, populated_db):
    """Verify that malformed JSON from Gemini gracefully falls back to deterministic engine."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client

    mock_response = MagicMock()
    mock_response.text = "NOT_VALID_JSON"
    mock_client.models.generate_content.return_value = mock_response

    # Question is recognizable by fallback
    res = process_query(
        "What is the total revenue?",
        db_path=populated_db,
        api_key="AIzaSyMockKey"
    )
    assert res.engine == "deterministic_fallback"
    assert res.intent == "TOTAL_REVENUE"
    assert "₹1,439,200.00" in res.answer

@patch("google.genai.Client")
def test_gemini_network_exception_fallback(mock_client_class, populated_db):
    """Verify that network exceptions during Gemini call fall back to deterministic engine."""
    mock_client = MagicMock()
    mock_client_class.return_value = mock_client
    mock_client.models.generate_content.side_effect = RuntimeError("Connection timeout to Gemini API")

    res = process_query(
        "Which product generated the highest revenue?",
        db_path=populated_db,
        api_key="AIzaSyMockKey"
    )
    assert res.engine == "deterministic_fallback"
    assert res.intent == "TOP_PRODUCT"
    assert "Monitor" in res.answer
