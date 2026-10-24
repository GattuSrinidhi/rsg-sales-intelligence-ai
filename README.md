# RSG Sales Intelligence AI Assistant

> **Official AI-Assisted Development Challenge for Graduate Engineer Trainee (GET) Selection**  
> A full-stack Business Intelligence Assistant enabling natural language querying over sales transaction data, backed by a deterministic SQLite analytics engine and runtime Gemini AI integration with zero numerical hallucinations.

---

## 1. Project Overview

The **RSG Sales Intelligence AI Assistant** provides business stakeholders with transparent, instant, and verified answers to natural language sales queries.

### Key Architectural Highlights
* **Vectorless RAG Architecture**: Avoids imprecise vector embeddings for structured numerical data. Instead, it extracts structured intents via Gemini (or a deterministic fallback), validates parameters strictly with Pydantic, and routes queries exclusively to verified SQLite analytical functions.
* **100% Deterministic & Fact-Grounded**: All monetary and volume figures are calculated directly via indexed SQLite queries using documented business rules.
* **Dual-Engine Resilience**: Automatically falls back to a deterministic regex/pattern-matching classifier if `GEMINI_API_KEY` is not provided or if the network is unavailable.
* **Self-Contained Frontend**: Interactive Single Page Application (SPA) with responsive KPI cards, dynamic data tables, and a pure SVG monthly trend chart — zero build step or heavy node dependencies required.
* **Comprehensive Test Suite**: 78 automated unit, regression, and integration tests across database, analytics, agent, API, and static frontend mounting.

---

## 2. Supported Official Business Questions

The system natively supports the 5 official challenge questions and their natural language paraphrases:

1. **What is the total revenue?**  
   *Calculates Net Revenue (₹1,439,200.00), Gross Revenue (₹1,443,700.00), Total Discounts (₹4,500.00), Total Units (633), and Category/Channel breakdowns.*
2. **Which product generated the highest revenue?**  
   *Identifies `Monitor` (₹473,000.00 across 50 units) and provides full ranking with volume insights (e.g. `Wireless Mouse` leads in units sold with 228).*
3. **What is the monthly revenue trend?**  
   *Presents a chronological H1 2026 series with Month-over-Month (MoM) absolute ($\Delta ₹$) and percentage ($\Delta \%$) deltas, peak month (`2026-05`), and a responsive bar chart.*
4. **Which region generated the highest sales?**  
   *Resolves the ambiguity of "sales" by reporting both Net Revenue (₹) and Units Sold (Volume), identifying `South` as the unanimous leader in both.*
5. **How did revenue change between two months?** (e.g. *"How did revenue change between April and May?"*)  
   *Compares months chronologically, calculating baseline revenue, target revenue, absolute change (+₹77,800.00), and percentage change (+32.32%).*

---

## 3. Technology Stack

* **Backend Framework**: Python 3.12, FastAPI, Uvicorn
* **Database**: SQLite 3 (persistent file-based storage with indexed queries)
* **Data Processing**: Python standard library (`csv`, `datetime`, `re`) & pandas
* **AI SDK**: Official `google-genai` Python SDK (Gemini 2.5 Flash)
* **Validation**: Pydantic v2
* **Frontend**: HTML5, Modern Responsive CSS3, Vanilla JavaScript (ES6+), Pure SVG Charts
* **Testing**: Pytest, FastAPI `TestClient`, HTTPX

---

## 4. Quickstart & Local Setup Guide (Windows)

### Prerequisites
* Windows OS
* Python 3.12 installed on your system

### Step 1: Clone Repository & Create Virtual Environment
```powershell
# Navigate to the workspace directory
cd "C:\Users\srikar gattu\Desktop\srinidhi_rsg"

# Create a dedicated Python 3.12 virtual environment
py -3.12 -m venv .venv

# Activate the virtual environment
.\.venv\Scripts\Activate.ps1
```

### Step 2: Install Dependencies
```powershell
.\.venv\Scripts\pip install -r requirements.txt
```

### Step 3: Configure Environment Variables (Optional)
The application works **100% offline using its deterministic engine** without requiring an API key. To enable live Gemini AI integration:
1. Create a `.env` file in the root directory:
   ```powershell
   Copy-Item .env.example .env
   ```
2. Open `.env` and insert your Gemini API Key from [Google AI Studio](https://aistudio.google.com/):
   ```env
   GEMINI_API_KEY="your_api_key_here"
   GEMINI_MODEL="gemini-2.5-flash"
   ```

### Step 4: Ingest Sales Dataset into Database
Run the idempotent ingestion pipeline to populate `data/rsg_sales.db`:
```powershell
.\.venv\Scripts\python -m src.import_data
```
*Output: `Import completed. Total: 51, Valid for Revenue: 49, Flagged (Excluded): 2.`*

### Step 5: Start Application Server
```powershell
.\.venv\Scripts\python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --reload
```
*(If port 8000 is occupied on your machine, simply specify `--port 8001`)*

### Step 6: Access the Application
* **Interactive Web Dashboard**: Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.
* **Interactive Swagger API Docs**: Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs).
* **Alternative ReDoc API Docs**: Open [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc).

---

## 5. Automated Testing

To run the complete automated test suite (78 tests covering database integrity, analytical formulas, agent parsing, API contracts, and static file mounting):

```powershell
.\.venv\Scripts\python -m pytest -v
```

External Gemini API calls are mocked in unit tests, guaranteeing that the full test suite runs in under 5 seconds with zero external dependencies.

---

## 6. Project Architecture & Directory Structure

```text
srinidhi_rsg/
│
├── .gitignore                      # Protects .env, *.db, and virtual environment
├── .env.example                    # Template for environment settings
├── requirements.txt                # Pinned production dependencies
├── pytest.ini                       # Test discovery and pythonpath configuration
├── README.md                       # Setup, run, and architecture documentation
│
├── data/
│   ├── sales_data.csv              # Official sales transaction source dataset
│   └── rsg_sales.db                # SQLite database (generated, untracked)
│
├── docs/
│   ├── ANALYTICS_SPEC.md           # Business formulas, ground truth benchmarks, rules
│   ├── AGENT_SPEC.md               # Vectorless RAG architecture, Pydantic schemas
│   └── API_SPEC.md                 # REST API endpoints, schemas, error codes
│
├── src/
│   ├── __init__.py
│   ├── config.py                   # Paths, environment configuration, constants
│   ├── db.py                       # SQLite connection factory, schema, safe queries
│   ├── import_data.py              # Idempotent CSV ingestion & defensive validation
│   ├── analytics.py                # Deterministic calculation engine for 5 questions
│   ├── agent.py                    # Vectorless RAG Agent & Gemini / Fallback router
│   └── main.py                     # FastAPI application, CORS, static mounting
│
├── frontend/
│   ├── index.html                  # Accessible Single Page Application
│   ├── styles.css                  # Modern responsive BI styling (Dark/Navy theme)
│   └── app.js                      # Client state, API caller, pure SVG chart generator
│
└── tests/
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures (in-memory DB, populated DB)
    ├── test_db.py                  # Database & defensive ingestion tests (12 tests)
    ├── test_analytics.py           # Mathematical regression tests against ground truth (12 tests)
    ├── test_agent.py               # Intent parsing, parameter extraction, fallback (30 tests)
    └── test_api.py                 # FastAPI endpoints, validation, error handling (24 tests)
```

---

## 7. Business Rules & Financial Data Integrity

1. **Formula**:
   $$\text{Gross Revenue} = \text{Quantity} \times \text{Unit Price}$$
   $$\text{Net Revenue} = \text{Gross Revenue} - \text{Discount Amount}$$
2. **Status Eligibility**: Only transactions with `Status = 'Completed'` count toward top-line revenue. Returned transactions (`TXN0033`, ₹19,000 gross) are excluded from revenue.
3. **Missing Prices**: Transaction `TXN0051` (Laptop Stand) is missing its unit price. In accordance with financial auditability, it is preserved in SQLite, flagged as `MISSING_UNIT_PRICE`, and excluded from revenue sums rather than fabricating prices.
4. **Zero Quantity**: Transaction `TXN0034` (Quantity = 0) is preserved as a valid zero-revenue transaction.
5. **Security**: No arbitrary SQL generation is permitted. All user queries map to allowlisted analytical functions with parameterized SQL.
