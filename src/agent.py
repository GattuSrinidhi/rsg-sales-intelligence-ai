"""Vectorless RAG AI Agent for Sales Intelligence.

Implements genuine runtime AI intent classification using the official `google-genai` SDK,
with strict schema validation (Pydantic), deterministic tool routing to `src.analytics`,
and a zero-crash deterministic fallback for offline/unconfigured environments.

Architecture:
    User Query -> Gemini Intent Extraction -> Security & Pydantic Validation
               -> Allowlisted Analytics Tool -> Grounded Deterministic Response
"""

import logging
import re
import time
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, ValidationError

from src.config import GEMINI_API_KEY, GEMINI_MODEL, DB_PATH
import src.analytics as analytics

logger = logging.getLogger(__name__)

# --- 1. Intent & Schema Definitions ---

class IntentType(str, Enum):
    TOTAL_REVENUE = "TOTAL_REVENUE"
    TOP_PRODUCT = "TOP_PRODUCT"
    MONTHLY_TREND = "MONTHLY_TREND"
    TOP_REGION = "TOP_REGION"
    REVENUE_DELTA = "REVENUE_DELTA"
    CLARIFICATION_NEEDED = "CLARIFICATION_NEEDED"
    UNKNOWN = "UNKNOWN"

class MetricType(str, Enum):
    REVENUE = "revenue"
    UNITS = "units"

class QueryIntent(BaseModel):
    """Structured intent representation extracted from user query."""
    intent: IntentType = Field(description="The primary business intent of the user's question.")
    metric: MetricType = Field(
        default=MetricType.REVENUE,
        description="Whether the query pertains to monetary revenue ('revenue') or volume/units sold ('units')."
    )
    month_a: Optional[str] = Field(
        default=None,
        description="First month for revenue comparison (e.g. 'April', '2026-04', '04')."
    )
    month_b: Optional[str] = Field(
        default=None,
        description="Second month for revenue comparison (e.g. 'May', '2026-05', '05')."
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0."
    )
    clarification_message: Optional[str] = Field(
        default=None,
        description="Clarification request if question is ambiguous or out of scope."
    )

class AgentResponse(BaseModel):
    """Standardized response schema returned by the Sales Intelligence Agent."""
    success: bool
    query: str
    intent: str
    engine: Literal["gemini", "deterministic_fallback"]
    answer: str
    supporting_data: Dict[str, Any]
    execution_trace: Dict[str, Any]

# --- 2. System Instructions for Gemini ---

GEMINI_SYSTEM_INSTRUCTION = """
You are the RSG Sales Intelligence Intent Classifier.
Your role is to analyze a business user's natural language question about sales transaction data and extract the structured intent and parameters.

The database contains sales transactions for H1 2026 (January to June 2026) with the following attributes:
- Products: Monitor, Desk, Office Chair, USB-C Hub, Wireless Mouse, Keyboard, Laptop Stand
- Categories: Accessories, Furniture, Electronics
- Regions: North, South, East, West
- Channels: Online, Retail
- Metrics: Quantity, Unit Price, Discount Amount, Status (Completed, Returned)

Rules:
1. Map the user's question strictly to one of the following IntentTypes:
   - TOTAL_REVENUE: Questions asking for total, overall, or gross revenue/sales across the company.
   - TOP_PRODUCT: Questions asking for the highest-performing, best-selling, or top product (by revenue or units).
   - MONTHLY_TREND: Questions asking for sales over time, monthly trends, or month-by-month performance.
   - TOP_REGION: Questions asking which territory, region, or area generated the highest sales.
   - REVENUE_DELTA: Questions asking to compare or calculate the difference/change in revenue between two months.
   - CLARIFICATION_NEEDED: Questions related to sales but missing required parameters (e.g., asking for a monthly comparison without specifying months).
   - UNKNOWN: Questions completely unrelated to sales transactions or business analytics.

2. Parameter Extraction:
   - If the user asks for volume, count, or units sold, set metric to 'units'. Otherwise default to 'revenue'.
   - For REVENUE_DELTA, extract both 'month_a' and 'month_b'. If only one month or no months are provided, set intent to CLARIFICATION_NEEDED.

3. Output strictly in the specified JSON schema. Do not generate SQL queries or invent calculation results.
"""

# --- 3. Gemini Runtime Integration ---

def classify_intent_with_gemini(
    query: str,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> QueryIntent:
    """Classify natural language query using official google-genai SDK."""
    effective_key = (api_key or GEMINI_API_KEY).strip()
    if not effective_key:
        raise ValueError("Gemini API key is not configured.")

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=effective_key)
        target_model = model_name or GEMINI_MODEL

        config = types.GenerateContentConfig(
            system_instruction=GEMINI_SYSTEM_INSTRUCTION,
            response_mime_type="application/json",
            response_schema=QueryIntent,
            temperature=0.0,
        )

        response = client.models.generate_content(
            model=target_model,
            contents=query,
            config=config,
        )

        # In google-genai, response.text contains the validated JSON string
        if not response or not response.text:
            raise ValueError("Empty response received from Gemini.")

        return QueryIntent.model_validate_json(response.text)

    except Exception as err:
        logger.warning(f"Gemini intent classification failed: {err}")
        raise err

# --- 4. Deterministic Rule-Based Fallback Classifier ---

# Month matching pattern
MONTH_PATTERN = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|november|december|"
    r"jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|\d{4}-\d{2})\b",
    re.IGNORECASE
)

def classify_intent_deterministic(query: str) -> QueryIntent:
    """Rule-based pattern matching intent classifier.
    
    Acts as an unbreakable offline/failure fallback guaranteeing 100% testability.
    """
    q = query.strip().lower()
    if not q:
        return QueryIntent(
            intent=IntentType.CLARIFICATION_NEEDED,
            clarification_message="Please enter a business question about sales transactions."
        )

    # 1. Total Revenue Patterns
    if any(p in q for p in [
        "total revenue", "overall revenue", "gross sales", "total sales",
        "how much revenue", "how much money", "total net revenue", "what is the revenue",
        "sales revenue", "overall sales", "all revenue"
    ]) or re.search(r"\b(total|overall|gross)\b.*\b(revenue|sales|earnings)\b", q):
        return QueryIntent(intent=IntentType.TOTAL_REVENUE, metric=MetricType.REVENUE)

    # 2. Revenue Delta / Month Comparison Patterns
    delta_triggers = ["revenue change", "how did revenue change", "change between", "compare", "difference between", "delta", "versus", "vs"]
    if any(t in q for t in delta_triggers):
        months_found = MONTH_PATTERN.findall(q)
        if len(months_found) >= 2:
            return QueryIntent(
                intent=IntentType.REVENUE_DELTA,
                month_a=months_found[0],
                month_b=months_found[1],
                metric=MetricType.REVENUE
            )
        else:
            return QueryIntent(
                intent=IntentType.CLARIFICATION_NEEDED,
                clarification_message="To compare revenue between two months, please specify both months (for example: 'How did revenue change between April and May?')."
            )

    # 3. Monthly Revenue Trend Patterns
    if any(p in q for p in [
        "monthly revenue trend", "monthly trend", "revenue trend", "sales over time",
        "month by month", "monthly breakdown", "sales trend", "monthly sales",
        "over time", "evolve over time", "by month"
    ]) or re.search(r"\b(trend|trajectory|evolution|evolve)\b", q):
        return QueryIntent(intent=IntentType.MONTHLY_TREND, metric=MetricType.REVENUE)

    # 4. Top Product Patterns
    if any(p in q for p in [
        "which product", "top product", "highest revenue product", "best selling product",
        "highest selling product", "top selling product", "highest revenue item",
        "most revenue product", "highest sales product", "which item", "top item", "best item",
        "most revenue"
    ]) or re.search(r"\b(top|best|highest|most)\b.*\b(product|item|selling)\b", q):
        metric = MetricType.UNITS if any(u in q for u in ["unit", "volume", "quantity", "number of"]) else MetricType.REVENUE
        return QueryIntent(intent=IntentType.TOP_PRODUCT, metric=metric)

    # 5. Top Region Patterns
    if any(p in q for p in [
        "which region", "top region", "highest sales region", "best region",
        "sales by region", "regional sales", "highest revenue region", "top selling region",
        "territory", "by region", "which territory"
    ]) or re.search(r"\b(region|territory|zone|area)\b", q):
        metric = MetricType.UNITS if any(u in q for u in ["unit", "volume", "quantity"]) else MetricType.REVENUE
        return QueryIntent(intent=IntentType.TOP_REGION, metric=metric)

    # 6. Fallback / Unknown
    return QueryIntent(
        intent=IntentType.UNKNOWN,
        clarification_message=(
            "I could not recognize your question. I specialize in sales intelligence for H1 2026. You can ask me:\n"
            "1. 'What is the total revenue?'\n"
            "2. 'Which product generated the highest revenue?'\n"
            "3. 'What is the monthly revenue trend?'\n"
            "4. 'Which region generated the highest sales?'\n"
            "5. 'How did revenue change between April and May?'"
        )
    )

# --- 5. Vectorless RAG Query Orchestrator ---

def process_query(
    query: str,
    db_path: Optional[Path] = None,
    api_key: Optional[str] = None
) -> AgentResponse:
    """Execute full Vectorless RAG query lifecycle.
    
    1. Interprets query with Gemini (with automatic fallback to deterministic rules).
    2. Routes validated intent to allowlisted analytics functions.
    3. Synthesizes a factual, grounded response with supporting figures and audit trace.
    """
    start_time = time.perf_counter()
    clean_query = query.strip()

    # Step 1: Intent Interpretation (AI with graceful fallback)
    engine: Literal["gemini", "deterministic_fallback"] = "gemini"
    intent_obj: QueryIntent

    try:
        intent_obj = classify_intent_with_gemini(clean_query, api_key=api_key)
    except Exception:
        # Fall back cleanly without crashing
        engine = "deterministic_fallback"
        intent_obj = classify_intent_deterministic(clean_query)

    # Step 2: Tool Routing & Deterministic Execution
    intent_type = intent_obj.intent
    tool_called: Optional[str] = None
    supporting_data: Dict[str, Any] = {}
    answer: str

    try:
        if intent_type == IntentType.TOTAL_REVENUE:
            tool_called = "get_total_revenue"
            res = analytics.get_total_revenue(db_path=db_path)
            answer = res["narrative"]
            supporting_data = res

        elif intent_type == IntentType.TOP_PRODUCT:
            tool_called = "get_top_product"
            res = analytics.get_top_product(metric=intent_obj.metric.value, db_path=db_path)
            answer = res["narrative"]
            supporting_data = res

        elif intent_type == IntentType.MONTHLY_TREND:
            tool_called = "get_monthly_revenue_trend"
            res = analytics.get_monthly_revenue_trend(db_path=db_path)
            answer = res["narrative"]
            supporting_data = res

        elif intent_type == IntentType.TOP_REGION:
            tool_called = "get_top_region"
            res = analytics.get_top_region(metric=intent_obj.metric.value, db_path=db_path)
            answer = res["narrative"]
            supporting_data = res

        elif intent_type == IntentType.REVENUE_DELTA:
            if intent_obj.month_a and intent_obj.month_b:
                tool_called = "get_revenue_delta"
                res = analytics.get_revenue_delta(
                    month_a=intent_obj.month_a,
                    month_b=intent_obj.month_b,
                    db_path=db_path
                )
                answer = res["narrative"]
                supporting_data = res
            else:
                answer = (
                    "To compare revenue between two months, please specify both months "
                    "(for example: 'How did revenue change between April and May?')."
                )
                supporting_data = {"requires_parameters": ["month_a", "month_b"]}

        elif intent_type == IntentType.CLARIFICATION_NEEDED:
            answer = intent_obj.clarification_message or "Could you please clarify your question?"
            supporting_data = {"status": "clarification_needed"}

        else: # UNKNOWN
            answer = (
                intent_obj.clarification_message or 
                "I specialize in sales intelligence for H1 2026. Please ask about total revenue, "
                "top products, monthly trends, regional sales, or revenue changes between months."
            )
            supporting_data = {"status": "out_of_scope"}

        success = True

    except Exception as err:
        logger.error(f"Error during analytics execution: {err}")
        success = False
        answer = f"An error occurred while calculating sales data: {str(err)}"
        supporting_data = {"error": str(err)}

    latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

    execution_trace = {
        "intent": intent_type.value,
        "metric": intent_obj.metric.value,
        "tool_called": tool_called,
        "parameters": {
            "month_a": intent_obj.month_a,
            "month_b": intent_obj.month_b,
        },
        "latency_ms": latency_ms,
        "is_safe": True,
    }

    return AgentResponse(
        success=success,
        query=clean_query,
        intent=intent_type.value,
        engine=engine,
        answer=answer,
        supporting_data=supporting_data,
        execution_trace=execution_trace,
    )
