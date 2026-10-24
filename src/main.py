"""FastAPI Backend Application for RSG Sales Intelligence AI Assistant.

Provides secure REST endpoints for natural language querying, health monitoring,
and direct access to deterministic analytics functions.
"""

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.agent import AgentResponse, process_query
import src.analytics as analytics
from src.config import DB_PATH, GEMINI_API_KEY
from src.db import execute_read_query, init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# --- 1. Lifespan Context Manager ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure database schema and tables exist on application startup."""
    try:
        init_db()
        logger.info("Database schema verified on startup.")
    except Exception as err:
        logger.error(f"Failed to initialize database on startup: {err}")
    yield

# --- 2. FastAPI Application Instance ---

app = FastAPI(
    title="RSG Sales Intelligence AI Assistant API",
    description=(
        "Production-grade Vectorless RAG assistant enabling business users to query "
        "sales data in natural language backed by deterministic SQLite queries."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# Narrow, secure CORS configuration for local development
ALLOWED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:8001",
    "http://127.0.0.1:8001",
    "http://localhost:3000",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# --- 3. Request & Response Schemas ---

class QueryRequest(BaseModel):
    """Input payload for natural language sales questions."""
    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural language question about sales transaction data.",
        examples=["What is the total revenue?"]
    )

class HealthResponse(BaseModel):
    """System health check response schema."""
    status: Literal["healthy", "degraded", "unhealthy"]
    version: str
    database_connected: bool
    gemini_configured: bool
    total_records: int
    valid_revenue_records: int
    timestamp: str

class ErrorResponse(BaseModel):
    """Standardized error response schema."""
    error: str
    error_type: str
    status_code: int

# --- 4. Exception Handlers (Security & No Leakage) ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle Pydantic request validation errors gracefully with 422."""
    first_error = exc.errors()[0] if exc.errors() else {}
    msg = first_error.get("msg", "Invalid request parameter.")
    loc = " -> ".join(str(l) for l in first_error.get("loc", []))
    detail = f"{msg} (field: {loc})" if loc else msg

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": detail,
            "error_type": "RequestValidationError",
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle standard HTTP exceptions with uniform structure."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "error_type": "HTTPException",
            "status_code": exc.status_code,
        }
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch unhandled errors, log internally, and return safe 500 without leaking stack trace."""
    logger.error(f"Unhandled server error: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "An internal server error occurred while processing your request.",
            "error_type": "InternalServerError",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        }
    )

# --- 5. Core API Endpoints ---

@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Check API and Database Health"
)
async def health_check():
    """Verify backend status, SQLite database connectivity, and configuration flags."""
    db_connected = False
    total_records = 0
    valid_records = 0

    try:
        rows = execute_read_query(
            "SELECT COUNT(*) AS total, SUM(is_valid_for_revenue) AS valid FROM sales_transactions;"
        )
        if rows:
            db_connected = True
            total_records = rows[0]["total"] or 0
            valid_records = rows[0]["valid"] or 0
    except Exception as err:
        logger.error(f"Health check database query failed: {err}")
        db_connected = False

    gemini_ready = bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())
    sys_status: Literal["healthy", "degraded", "unhealthy"] = (
        "healthy" if db_connected else "unhealthy"
    )

    return HealthResponse(
        status=sys_status,
        version="1.0.0",
        database_connected=db_connected,
        gemini_configured=gemini_ready,
        total_records=total_records,
        valid_revenue_records=valid_records,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

@app.post(
    "/api/query",
    response_model=AgentResponse,
    tags=["Sales Intelligence"],
    summary="Ask a Natural Language Sales Question"
)
async def query_sales_assistant(payload: QueryRequest):
    """Process natural language question through the Vectorless RAG Agent."""
    clean_question = payload.question.strip()
    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be blank or contain only whitespace."
        )

    # Execute query through trusted agent orchestrator
    response = process_query(clean_question)
    return response

# --- 6. Direct Deterministic Analytics Endpoints ---

@app.get(
    "/api/analytics/total-revenue",
    tags=["Analytics"],
    summary="Direct Deterministic Total Revenue Calculation"
)
async def api_total_revenue():
    """Calculate verified total net and gross revenue."""
    return analytics.get_total_revenue()

@app.get(
    "/api/analytics/top-product",
    tags=["Analytics"],
    summary="Direct Deterministic Top Product Analysis"
)
async def api_top_product(metric: str = "revenue"):
    """Identify top product by net revenue or units sold."""
    if metric not in ("revenue", "units"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metric parameter must be either 'revenue' or 'units'."
        )
    return analytics.get_top_product(metric=metric)

@app.get(
    "/api/analytics/monthly-trend",
    tags=["Analytics"],
    summary="Direct Deterministic Monthly Revenue Trend"
)
async def api_monthly_trend():
    """Retrieve monthly revenue trend with MoM deltas."""
    return analytics.get_monthly_revenue_trend()

@app.get(
    "/api/analytics/top-region",
    tags=["Analytics"],
    summary="Direct Deterministic Top Region Analysis"
)
async def api_top_region(metric: str = "revenue"):
    """Identify top sales region by net revenue or units sold."""
    if metric not in ("revenue", "units"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metric parameter must be either 'revenue' or 'units'."
        )
    return analytics.get_top_region(metric=metric)

@app.get(
    "/api/analytics/revenue-delta",
    tags=["Analytics"],
    summary="Direct Deterministic Revenue Delta Between Two Months"
)
async def api_revenue_delta(month_a: str, month_b: str):
    """Calculate revenue delta between two months."""
    try:
        return analytics.get_revenue_delta(month_a=month_a, month_b=month_b)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err)
        )

# --- 7. Static Frontend Dashboard Mounting ---

from fastapi.staticfiles import StaticFiles
from src.config import FRONTEND_DIR

if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host="127.0.0.1", port=8000, reload=True)
