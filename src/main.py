
"""FastAPI Backend Application for RSG Sales Intelligence AI Assistant.

Provides REST endpoints for natural language querying, health monitoring,
and direct access to deterministic analytics functions.
"""

import logging
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import uvicorn

from src.agent import AgentResponse, process_query
import src.analytics as analytics
from src.config import DB_PATH, GEMINI_API_KEY, FRONTEND_DIR
from src.db import execute_read_query
from src.import_data import import_sales_data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


# --- 1. Application Lifespan ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and import sales data on startup."""
    try:
        result = import_sales_data()
        logger.info("Sales data import completed: %s", result)
    except Exception:
        logger.exception("Failed to initialize or import sales data.")
        raise

    yield

# --- 2. FastAPI Application ---

app = FastAPI(
    title="RSG Sales Intelligence AI Assistant API",
    description=(
        "Sales intelligence assistant that answers natural-language "
        "questions using deterministic analytics backed by SQLite."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# --- 3. CORS Configuration ---

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
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# --- 4. Request and Response Schemas ---

class QueryRequest(BaseModel):
    """Input payload for natural-language sales questions."""

    question: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Natural-language question about sales transactions.",
        examples=["What is the total revenue?"],
    )


class HealthResponse(BaseModel):
    """System health check response."""

    status: str
    version: str
    database_connected: bool
    gemini_configured: bool
    total_records: int
    valid_revenue_records: int
    timestamp: str


# --- 5. Exception Handlers ---

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    """Return a consistent response for invalid requests."""

    first_error = exc.errors()[0] if exc.errors() else {}
    message = first_error.get("msg", "Invalid request parameter.")
    location = " -> ".join(
        str(item) for item in first_error.get("loc", [])
    )

    detail = f"{message} (field: {location})" if location else message

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": detail,
            "error_type": "RequestValidationError",
            "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(
    request: Request,
    exc: HTTPException,
):
    """Return a consistent response for HTTP errors."""

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "error_type": "HTTPException",
            "status_code": exc.status_code,
        },
        headers=exc.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    """Log unexpected errors and return a safe error response."""

    logger.error("Unhandled server error.", exc_info=True)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": (
                "An internal server error occurred "
                "while processing your request."
            ),
            "error_type": "InternalServerError",
            "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        },
    )


# --- 6. Core API Endpoints ---

@app.get(
    "/api/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Check API and database health",
)
async def health_check():
    """Check database connectivity and report record counts."""

    db_connected = False
    total_records = 0
    valid_records = 0

    try:
        rows = execute_read_query(
            """
            SELECT
                COUNT(*) AS total,
                SUM(is_valid_for_revenue) AS valid
            FROM sales_transactions;
            """
        )

        if rows:
            db_connected = True
            total_records = rows[0]["total"] or 0
            valid_records = rows[0]["valid"] or 0

    except Exception:
        logger.exception("Health-check database query failed.")

    gemini_ready = bool(
        GEMINI_API_KEY and GEMINI_API_KEY.strip()
    )

    system_status = "healthy" if db_connected else "unhealthy"

    return HealthResponse(
        status=system_status,
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
    summary="Ask a natural-language sales question",
)
async def query_sales_assistant(payload: QueryRequest):
    """Process a question using the sales intelligence agent."""

    clean_question = payload.question.strip()

    if not clean_question:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question cannot be blank or contain only whitespace.",
        )

    return process_query(clean_question)


# --- 7. Direct Deterministic Analytics Endpoints ---

@app.get(
    "/api/analytics/total-revenue",
    tags=["Analytics"],
    summary="Calculate total revenue",
)
async def api_total_revenue():
    """Return total net and gross revenue."""

    return analytics.get_total_revenue()


@app.get(
    "/api/analytics/top-product",
    tags=["Analytics"],
    summary="Analyze top products",
)
async def api_top_product(metric: str = "revenue"):
    """Find the top product by revenue or units sold."""

    if metric not in ("revenue", "units"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metric must be either 'revenue' or 'units'.",
        )

    return analytics.get_top_product(metric=metric)


@app.get(
    "/api/analytics/monthly-trend",
    tags=["Analytics"],
    summary="Retrieve monthly revenue trends",
)
async def api_monthly_trend():
    """Return monthly revenue trends."""

    return analytics.get_monthly_revenue_trend()


@app.get(
    "/api/analytics/top-region",
    tags=["Analytics"],
    summary="Analyze top sales regions",
)
async def api_top_region(metric: str = "revenue"):
    """Find the top region by revenue or units sold."""

    if metric not in ("revenue", "units"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Metric must be either 'revenue' or 'units'.",
        )

    return analytics.get_top_region(metric=metric)


@app.get(
    "/api/analytics/revenue-delta",
    tags=["Analytics"],
    summary="Compare revenue between two months",
)
async def api_revenue_delta(month_a: str, month_b: str):
    """Calculate the revenue difference between two months."""

    try:
        return analytics.get_revenue_delta(
            month_a=month_a,
            month_b=month_b,
        )
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(err),
        ) from err


# --- 8. Serve the Frontend ---

if FRONTEND_DIR.exists():
    app.mount(
        "/",
        StaticFiles(directory=str(FRONTEND_DIR), html=True),
        name="frontend",
    )
else:
    logger.warning(
        "Frontend directory was not found: %s",
        FRONTEND_DIR,
    )


# --- 9. Local Development Server ---

def is_port_in_use(port: int) -> bool:
    """Return whether a local TCP port is occupied."""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.settimeout(0.5)
        return server_socket.connect_ex(("127.0.0.1", port)) == 0


if __name__ == "__main__":
    target_port = 8000

    if is_port_in_use(target_port):
        logger.warning(
            "Port 8000 is occupied. Switching to port 8001."
        )
        target_port = 8001

    logger.info(
        "Starting RSG Sales Intelligence Assistant at "
        "http://127.0.0.1:%s",
        target_port,
    )

    uvicorn.run(
        "src.main:app",
        host="127.0.0.1",
        port=target_port,
        reload=True,
    )
