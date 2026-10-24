"""Configuration settings for the RSG Sales Intelligence AI Assistant."""

from pathlib import Path
import os
from dotenv import load_dotenv

# Base Project Paths
SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent
DATA_DIR = BASE_DIR / "data"
FRONTEND_DIR = BASE_DIR / "frontend"

# Load environment variables from .env if present
load_dotenv(BASE_DIR / ".env")

# Data File Paths
CSV_PRIMARY_PATH = DATA_DIR / "sales_data.csv"
CSV_FALLBACK_PATH = BASE_DIR / "ai_bi_assistant_sales_data - GET.csv"
DB_PATH = DATA_DIR / "rsg_sales.db"

def get_csv_path() -> Path:
    """Return the existing CSV file path."""
    if CSV_PRIMARY_PATH.exists():
        return CSV_PRIMARY_PATH
    if CSV_FALLBACK_PATH.exists():
        return CSV_FALLBACK_PATH
    raise FileNotFoundError(f"Sales CSV dataset not found at {CSV_PRIMARY_PATH} or {CSV_FALLBACK_PATH}")

# LLM & AI Settings
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()

# Business Rules Constants
REVENUE_QUALIFYING_STATUSES = {"Completed"}
EXCLUDED_STATUSES = {"Returned", "Cancelled"}
DATE_INPUT_FORMAT = "%d-%m-%Y"
DATE_DB_FORMAT = "%Y-%m-%d"
